"""Only explicitly shared, currently family-public evidence enters an admin queue."""
import hashlib
import re

from flask import abort
from access import family_role
from models import Draft,Interview,NewPerson,Person,new_id
from organizing import owned,member
from search_index import plain_text
from reporting import local_now


def public_story(s,fid,sid,lock=False):
    q=s.query(Interview).filter_by(id=sid,family_id=fid,del_flag=0)
    story=(q.with_for_update() if lock else q).populate_existing().first()
    if not story or (story.publish_status or 'published')!='published' or (story.visibility or 'public')!='public':return None,None
    q=s.query(Draft).filter_by(interview_id=story.id,is_current=True,del_flag=0).order_by(Draft.version.desc())
    draft=(q.with_for_update() if lock else q).populate_existing().first()
    return story,draft


def grounded(item,draft):
    return bool(draft and item.get('name') and item.get('evidence') and re.sub(r'\s+',' ',item['evidence']).strip() in plain_text(draft.content) and item['name'] in item['evidence'])


def readable(s,candidate):
    if not candidate.source_record_id:return True  # Existing imports keep their established contract.
    story,draft=public_story(s,candidate.family_id,candidate.interview_id)
    return bool(story and grounded({'name':candidate.name,'evidence':candidate.evidence},draft))


def source_context(s,record):
    if not record or not record.story_id or not record.preview:return None
    story,draft=public_story(s,record.family_id,record.story_id)
    return {'public':bool(story and story.author_id==record.user_id and draft),'version':draft.version if draft else 0,
        'people':[dict(item,index=i,shareable=grounded(item,draft)) for i,item in enumerate(record.preview.get('people',[]))]}


def share(s,fid,uid,rid,revision,preview_revision,story_version,indices):
    record=owned(s,fid,uid,rid,lock=True)
    if str(record.revision)!=str(revision) or str(record.preview_revision)!=str(preview_revision) or not record.story_id:abort(409,'原稿或预览已变化，请核对。')
    story,draft=public_story(s,fid,record.story_id,lock=True)
    if not story or story.author_id!=uid or not draft or str(draft.version)!=str(story_version):abort(409,'仅可提交本人已发布、全家可见的当前故事依据；请核对可见范围和版本。')
    rows=record.preview.get('people',[]) if record.preview else []
    selected=[]
    for index in set(indices):
        if not re.fullmatch(r'[0-9]{1,2}',index) or int(index)>=len(rows):abort(400,'人物建议编号无效')
        i=int(index);item=rows[i]
        if not grounded(item,draft):abort(409,'此条依据未出现在当前公开故事中，不能把私有原稿片段发送到家庭候选。')
        selected.append((i,item))
    if not selected:abort(400,'请选择要提交的人物建议')
    for index,item in selected:
        cid=hashlib.sha256(('site-person\0'+rid+'\0'+str(record.preview_revision)+'\0'+str(index)).encode()).hexdigest()
        if s.get(NewPerson,cid):continue
        s.add(NewPerson(id=cid,family_id=fid,interview_id=story.id,name=item['name'],context=item['evidence'],
            evidence=item['evidence'],source_record_id=rid,source_revision=record.revision,source_preview_revision=record.preview_revision,
            join_tree='pending',create_by=uid,create_date=local_now()))
    s.commit()


def review(s,fid,uid,cid,story_version,action,person_id=None,name='',duplicate=False):
    from transaction_locks import serialize_sqlite
    serialize_sqlite(s,uid);member(s,fid,uid)
    if family_role(s,fid,uid) not in ('owner','admin'):abort(403)
    candidate=s.query(NewPerson).filter_by(id=cid,family_id=fid,del_flag=0).first()
    if not candidate or not candidate.source_record_id:abort(404)
    story,draft=public_story(s,fid,candidate.interview_id,lock=True)
    if not story:abort(404)
    candidate=s.query(NewPerson).filter_by(id=cid).with_for_update().populate_existing().one()
    if candidate.join_tree=='joined':return candidate.linked_person_id
    if candidate.join_tree=='dismissed' and action=='dismiss':return None
    if candidate.join_tree!='pending' or not draft or str(draft.version)!=str(story_version) or not grounded({'name':candidate.name,'evidence':candidate.evidence},draft):abort(409,'来源故事或建议已变化，请重新核对。')
    if action=='dismiss':candidate.join_tree='dismissed'
    elif action in ('link','create'):
        if action=='link':
            person=s.query(Person).filter_by(id=person_id,family_id=fid,del_flag=0).first()
            if not person:abort(400,'请选择本家庭现有人物，不会自动猜测同名对应关系。')
        else:
            name=name.strip()
            if not name or len(name)>100:abort(400,'请填写人物姓名或暂存称谓，最多100字。')
            existing=s.query(Person.id).filter_by(family_id=fid,name=name,del_flag=0).first()
            if existing and not duplicate:abort(409,'家庭中已有同名人物。请手动关联，或明确确认这是另一位同名人物。')
            person=Person(id=new_id(),family_id=fid,name=name,status='pending',life_status='unknown',
                notes=['来源于已公开故事的人物建议，关系与身份尚待核对。'],create_by=uid)
            s.add(person)
        candidate.linked_person_id=person.id;candidate.join_tree='joined'
    else:abort(400,'请选择有效的审核操作。')
    candidate.reviewed_by=uid;candidate.update_date=local_now();s.commit();return candidate.linked_person_id
