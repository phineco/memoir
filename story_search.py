"""Portable SQL filtering with identical family/story visibility before counting."""
import datetime
import math

from sqlalchemy import func,or_
from flask import abort

from models import Draft,Interview,Person,Quote


FIELDS=('q','subject','narrator','period_from','period_to','published_from','published_to','sort')


def search(s,family_id,me,args,visible_filter,published_only):
    values={name:args.get(name,'').strip() for name in FIELDS}
    if len(values['q'])>200:abort(400,'关键词最多 200 字')
    try:page=int(args.get('page','1'))
    except (ValueError,TypeError):abort(400,'页码无效')
    if page<1:abort(400,'页码无效')
    values['sort']=values['sort'] or 'published_desc'
    if values['sort'] not in ('published_desc','period_asc','period_desc'):abort(400,'排序无效')
    people=s.query(Person).filter_by(family_id=family_id,del_flag=0).order_by(Person.sort,Person.id).all()
    ids={person.id for person in people}
    for field in ('subject','narrator'):
        if values[field] and values[field] not in ids:abort(400,'人物筛选无效')
    dates={}
    for field in ('period_from','period_to','published_from','published_to'):
        try:dates[field]=datetime.date.fromisoformat(values[field]) if values[field] else None
        except ValueError:abort(400,'日期格式应为年-月-日')
    for prefix in ('period','published'):
        if dates[prefix+'_from'] and dates[prefix+'_to'] and dates[prefix+'_from']>dates[prefix+'_to']:
            abort(400,'开始日期不能晚于结束日期')
    q=visible_filter(s.query(Interview).filter_by(family_id=family_id,del_flag=0),s,me)
    if values['q']:
        escaped=values['q'].replace('\\','\\\\').replace('%','\\%').replace('_','\\_')
        pattern='%'+escaped+'%'
        drafts=s.query(Draft.id).filter(Draft.interview_id==Interview.id,Draft.is_current.is_(True),Draft.del_flag==0,Draft.search_text.ilike(pattern,escape='\\')).exists()
        quotes=s.query(Quote.id).filter(Quote.interview_id==Interview.id,Quote.del_flag==0,
            or_(Quote.status!='dropped',Quote.status.is_(None)),Quote.text.ilike(pattern,escape='\\')).exists()
        q=q.filter(or_(Interview.topic.ilike(pattern,escape='\\'),drafts,quotes))
    if values['subject']:q=q.filter(Interview.person_id==values['subject'])
    if values['narrator']:q=q.filter(Interview.narrator_person_id==values['narrator'])
    if dates['period_from']:q=q.filter(func.coalesce(Interview.period_end,Interview.period_start)>=dates['period_from'])
    if dates['period_to']:q=q.filter(func.coalesce(Interview.period_start,Interview.period_end)<=dates['period_to'])
    publication=func.coalesce(Interview.published_at,Interview.create_date)
    if dates['published_from'] or dates['published_to']:
        q=q.filter(published_only())
        if dates['published_from']:q=q.filter(publication>=datetime.datetime.combine(dates['published_from'],datetime.time()))
        if dates['published_to']:
            q=q.filter(func.date(publication)<=dates['published_to'].isoformat())
    total=q.count();pages=max(1,math.ceil(total/20));page=min(page,pages)
    if values['sort']=='published_desc':ordering=(publication.desc(),Interview.id)
    else:
        period=func.coalesce(Interview.period_start,Interview.period_end)
        ordering=(period.is_(None),period.asc() if values['sort']=='period_asc' else period.desc(),Interview.id)
    rows=q.add_entity(Person).outerjoin(Person,Interview.person_id==Person.id).order_by(*ordering).limit(20).offset((page-1)*20).all()
    active=any(value for name,value in values.items() if name!='sort') or values['sort']!='published_desc'
    return dict(rows=rows,filters=values,people=people,total=total,page=page,pages=pages,filtered=active)
