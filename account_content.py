"""Personal content is aggregated only across current family memberships."""
import math

from flask import abort
from sqlalchemy import func, or_

from models import Interview, InterviewPerson, Person


def listing(s, me, families, args, visible_filter, *, drafts=False):
    kind = 'drafts' if drafts else args.get('kind', 'own')
    if kind not in ('drafts', 'own', 'about'):abort(400, '个人内容分类无效')
    scope = args.get('scope_family', '')
    if scope and scope not in families:abort(404)
    keyword = args.get('q', '').strip()
    if len(keyword)>200:abort(400, '标题关键词最多 200 字')
    try:page=int(args.get('page', '1'))
    except ValueError:abort(400, '页码无效')
    if page<1:abort(400, '页码无效')
    q = visible_filter(s.query(Interview).filter(Interview.del_flag==0,
        Interview.family_id.in_([scope] if scope else list(families))), s, me)
    if drafts:
        q=q.filter(Interview.author_id==me.id, Interview.publish_status=='draft')
    else:
        q=q.filter(or_(Interview.publish_status=='published',Interview.publish_status.is_(None)))
        if kind=='own':q=q.filter(Interview.author_id==me.id)
        else:
            primary=s.query(Person.id).filter(Person.id==Interview.person_id,
                Person.family_id==Interview.family_id,Person.user_id==me.id,Person.del_flag==0).exists()
            related=s.query(InterviewPerson.id).join(Person, Person.id==InterviewPerson.person_id).filter(
                InterviewPerson.interview_id==Interview.id,InterviewPerson.del_flag==0,
                Person.family_id==Interview.family_id,Person.user_id==me.id,Person.del_flag==0).exists()
            q=q.filter(or_(primary,related))
    if keyword:q=q.filter(Interview.topic.contains(keyword,autoescape=True))
    total=q.count();pages=max(1,math.ceil(total/20));page=min(page,pages)
    rows=q.order_by(func.coalesce(Interview.published_at,Interview.create_date).desc(),Interview.id).offset((page-1)*20).limit(20).all()
    return dict(rows=rows,kind=kind,scope_family=scope,keyword=keyword,total=total,pages=pages,page=page,
                content_families=families)
