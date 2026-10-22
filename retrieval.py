"""Bounded lexical retrieval over authorized family-public story paragraphs."""
import html
import re

from access import family_role
from models import Draft, Interview, get_session


def terms(text):
    text=re.sub(r'\s+','',text.lower())
    tokens=set(re.findall(r'[a-z0-9]{2,}',text))
    for run in re.findall(r'[\u4e00-\u9fff]+',text):
        tokens.update(run[i:i+2] for i in range(len(run)-1))
    return tokens-{'什么','时候','哪年','怎么','我们','家里','事情','一下','帮我','关于'}


def retrieve(family_id, user_id, question, max_sources=6):
    s=get_session()
    if not family_role(s,family_id,user_id):return []
    wanted=terms(question);candidates=[]
    rows=s.query(Interview,Draft).join(Draft,Draft.interview_id==Interview.id).filter(
        Interview.family_id==family_id,Interview.del_flag==0,Draft.del_flag==0,Draft.is_current.is_(True)).order_by(Interview.create_date.desc(),Interview.id).all()
    for iv,d in rows:
        if (iv.publish_status or 'published')!='published' or (iv.visibility or 'public')!='public':continue
        body=html.unescape(re.sub(r'<[^>]+>','\n',d.content or ''))
        chunks=[]
        for paragraph in re.split(r'[\n]+',body):
            paragraph=paragraph.strip()
            if paragraph:
                chunks.extend(paragraph[i:i+420] for i in range(0,len(paragraph),340))
        for number,chunk in enumerate(chunks):
            score=len(wanted & terms(chunk)) + 3*len(wanted & terms(iv.topic or ''))
            candidates.append((score,iv.id,number,iv.topic or '未命名',chunk))
    # A broad summary can use recent representative excerpts, but no match is never proof of absence.
    candidates.sort(key=lambda row:-row[0])
    positive=[row for row in candidates if row[0]>0]
    selected=positive if positive else candidates
    result=[];per_story={}
    for score,sid,number,title,excerpt in selected:
        if per_story.get(sid,0)>=2:continue
        result.append({'index':len(result)+1,'story_id':sid,'title':title,'excerpt':excerpt,'matched':score>0})
        per_story[sid]=per_story.get(sid,0)+1
        if len(result)>=max_sources:break
    return result
