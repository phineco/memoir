"""A story can suggest doing, never silently mark a person's whole plan done."""
import hashlib
import json

from flask import abort
from access import family_role
from models import PlanProgressSuggestion,Person,WritingPlan,new_id
from organizing import owned,member
from people_suggestions import public_story
from reporting import local_now


def items(plan):
    try:value=json.loads(plan.items or '[]')
    except (ValueError,TypeError):return []
    return value if isinstance(value,list) else []


def stamp(plan):
    return hashlib.sha256(json.dumps([plan.title,plan.status,plan.items,str(plan.update_date)],ensure_ascii=False).encode()).hexdigest()


def eligible(s,plan,story,index):
    rows=items(plan)
    return bool(plan.family_id==story.family_id and plan.status=='active' and 0<=index<len(rows)
        and isinstance(rows[index],dict) and rows[index].get('person_id')==story.person_id
        and rows[index].get('status','pending')=='pending'
        and s.query(Person.id).filter_by(id=story.person_id,family_id=story.family_id,del_flag=0).first())


def options(s,record):
    if not record or not record.story_id:return []
    story,draft=public_story(s,record.family_id,record.story_id)
    if not story or story.author_id!=record.user_id or not draft:return []
    out=[]
    for plan in s.query(WritingPlan).filter_by(family_id=record.family_id,status='active',del_flag=0).all():
        for i,item in enumerate(items(plan)):
            if eligible(s,plan,story,i):out.append({'plan_id':plan.id,'title':plan.title,'index':i,'stamp':stamp(plan),'version':draft.version})
    return out


def propose(s,fid,uid,rid,plan_id,index,expected_stamp,story_version):
    record=owned(s,fid,uid,rid,lock=True)
    story,draft=public_story(s,fid,record.story_id,lock=True)
    if not story or story.author_id!=uid or not draft or str(draft.version)!=str(story_version):abort(409,'只有本人已发布且全家可见的当前故事，可建议共享计划进度。')
    plan=s.query(WritingPlan).filter_by(id=plan_id,family_id=fid,del_flag=0).with_for_update().populate_existing().first()
    try:index=int(index)
    except (TypeError,ValueError):abort(400)
    if not plan or stamp(plan)!=expected_stamp or not eligible(s,plan,story,index):abort(409,'计划条目已变化，请重新核对。')
    sid=hashlib.sha256(('plan-suggestion\0'+story.id+'\0'+str(draft.version)+'\0'+plan.id+'\0'+str(index)+'\0'+expected_stamp).encode()).hexdigest()
    old=s.query(PlanProgressSuggestion).filter_by(id=sid).with_for_update().populate_existing().first()
    if old:return old
    row=PlanProgressSuggestion(id=sid,family_id=fid,user_id=uid,record_id=rid,story_id=story.id,story_version=draft.version,
        person_id=story.person_id,plan_id=plan.id,item_index=index,plan_stamp=expected_stamp,status='pending',create_by=uid,create_date=local_now())
    s.add(row);s.commit();return row


def review(s,fid,uid,sid,action):
    from transaction_locks import serialize_sqlite
    serialize_sqlite(s,uid)
    if member(s,fid,uid,lock=True) not in ('owner','admin'):abort(403)
    row=s.query(PlanProgressSuggestion).filter_by(id=sid,family_id=fid,del_flag=0).first()
    if not row:abort(404)
    story,draft=public_story(s,fid,row.story_id,lock=True)
    if not story:abort(404)
    plan=s.query(WritingPlan).filter_by(id=row.plan_id,family_id=fid,del_flag=0).with_for_update().populate_existing().first()
    row=s.query(PlanProgressSuggestion).filter_by(id=sid).with_for_update().populate_existing().one()
    if row.status in ('applied','dismissed'):return row
    if row.status!='pending':abort(409,'建议已撤回或已失效，请重新核对。')
    if action=='dismiss':row.status='dismissed'
    elif action=='apply':
        if not draft or draft.version!=row.story_version or not plan or stamp(plan)!=row.plan_stamp or not eligible(s,plan,story,row.item_index):abort(409,'故事或计划已有变化，请核对后重新提出建议。')
        values=items(plan);values[row.item_index]=dict(values[row.item_index],status='doing')
        plan.items=json.dumps(values,ensure_ascii=False);plan.update_by=uid;plan.update_date=local_now()
        row.status='applied'
    else:abort(400,'操作无效')
    row.reviewed_by=uid;row.update_date=local_now();s.commit();return row


def pending(s,fid):
    out=[]
    for row in s.query(PlanProgressSuggestion).filter_by(family_id=fid,status='pending',del_flag=0).order_by(PlanProgressSuggestion.create_date).limit(50):
        story,draft=public_story(s,fid,row.story_id)
        plan=s.query(WritingPlan).filter_by(id=row.plan_id,family_id=fid,del_flag=0).first()
        if story and draft and draft.version==row.story_version and plan and stamp(plan)==row.plan_stamp and eligible(s,plan,story,row.item_index):
            out.append((row,story,plan))
    return out
