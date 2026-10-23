"""Synchronous AI attempts with durable status, cancellation and idempotency."""
import datetime
import hashlib
import re

from flask import url_for
from sqlalchemy.exc import IntegrityError

from access import family_role
from models import AiMessage,AiTurn,get_session
import ai


class TurnConflict(Exception):pass


def turn_id(family_id,user_id,nonce):
    if not isinstance(nonce,str) or not re.fullmatch(r'[a-zA-Z0-9_-]{8,80}',nonce):
        raise ValueError('无效请求编号')
    return hashlib.sha256((family_id+':'+user_id+':'+nonce).encode()).hexdigest()


def lookup(family_id,user_id,nonce):
    return get_session().query(AiTurn).filter_by(id=turn_id(family_id,user_id,nonce),family_id=family_id,user_id=user_id,del_flag=0).first()


def public_result(turn):
    current=ai.user_context_stamp(turn.family_id,turn.user_id)
    if turn.context_stamp!=current:
        return {'status':'outdated','question':turn.question,'answer':'','sources':[], 'error':'资料范围已变化，请核对后重新提问。'}
    if turn.status=='running' and turn.lease_until and turn.lease_until<datetime.datetime.now():
        s=get_session();s.query(AiTurn).filter_by(id=turn.id,status='running').update({AiTurn.status:'failed',AiTurn.error:'连接已中断，问题已保留，请手动重试。'});s.commit();s.refresh(turn)
    sources=[]
    for row in turn.sources or []:
        sources.append(dict(row,url=url_for('main.story_detail',family_id=turn.family_id,interview_id=row['story_id'])+'#articleBody'))
    return {'status':turn.status,'question':turn.question,'answer':turn.answer or '', 'error':turn.error or '', 'sources':sources}


def begin(family_id,user_id,nonce,message,retry_of=None):
    s=get_session()
    from ai_memory import preference
    preference(family_id,user_id,create=True);s.commit()
    prior=lookup(family_id,user_id,nonce)
    if prior:
        if prior.question!=message:raise TurnConflict('请求编号已用于另一个问题')
        return prior,False
    stamp=ai.user_context_stamp(family_id,user_id)
    logical_id=turn_id(family_id,user_id,nonce)
    if retry_of is not None:
        parent=lookup(family_id,user_id,retry_of)
        if not parent or parent.question!=message:raise TurnConflict('重试来源无效')
        if parent.context_stamp==stamp:
            if parent.status not in ('failed','cancelled'):raise TurnConflict('原请求仍在处理或已经完成')
            logical_id=parent.logical_id or parent.id
    from retrieval import retrieve
    turn=AiTurn(id=turn_id(family_id,user_id,nonce),family_id=family_id,user_id=user_id,question=message,
                logical_id=logical_id,status='running',answer='',remarks=nonce,context_stamp=stamp,sources=retrieve(family_id,user_id,message),
                lease_until=datetime.datetime.now()+datetime.timedelta(minutes=5),create_by=user_id)
    s.add(turn)
    try:s.commit()
    except IntegrityError:
        s.rollback();return lookup(family_id,user_id,nonce),False
    return turn,True


def cancelled_or_changed(turn):
    s=get_session();s.commit();s.expire_all();s.refresh(turn)
    return (turn.status!='running' or not family_role(s,turn.family_id,turn.user_id)
            or ai.user_context_stamp(turn.family_id,turn.user_id)!=turn.context_stamp)


def generate(turn,family_name):
    s=get_session();parts=[];complete=False
    source=None
    try:
        if cancelled_or_changed(turn):raise ai.AIError("请求已停止")
        source=ai.chat_stream(turn.family_id,turn.user_id,turn.question,family_name=family_name,persist=False,expected_stamp=turn.context_stamp)
        yield {'sources':public_result(turn)['sources']}
        for piece in source:
            if cancelled_or_changed(turn):
                raise ai.AIError('已停止生成或资料范围发生变化，问题已保留。')
            parts.append(piece);yield {'chunk':piece}
        if not parts:raise ai.AIError('未收到完整回复，请稍后重试。')
        if cancelled_or_changed(turn):raise ai.AIError('已停止生成或资料范围发生变化。')
        s.rollback()
        from ai_memory import guard_write
        if not guard_write(turn.family_id,turn.user_id,turn.context_stamp):raise ai.AIError('AI 记忆已重置')
        now=datetime.datetime.now();answer=''.join(parts)
        claimed=s.query(AiTurn).filter_by(id=turn.id,status='running').update({
            AiTurn.status:'succeeded',AiTurn.answer:answer, AiTurn.update_date:now},synchronize_session=False)
        if not claimed:s.rollback();raise ai.AIError('生成已取消')
        for role,content in [('user',turn.question),('assistant',answer)]:
            s.add(AiMessage(id=hashlib.sha256((turn.id+role).encode()).hexdigest(),family_id=turn.family_id,user_id=turn.user_id,
                            role=role,content=content[:12000],remarks=turn.context_stamp,create_by=turn.user_id,create_date=now))
        s.commit();complete=True
        yield {'complete':True}
    except GeneratorExit:
        raise
    except Exception as error:
        from observability import record_error
        record_error(error,'ai_stream')
        s.rollback();s.expire_all()
        s.query(AiTurn).filter_by(id=turn.id,status='running').update({AiTurn.status:'failed',AiTurn.answer:''.join(parts),AiTurn.error:'生成未完成，问题已保留，可核对后重试。'})
        s.commit();yield {'error':'生成未完成，问题已保留，可核对后重试。'}
    finally:
        if hasattr(source,'close'):source.close()
        if not complete:
            s.rollback()
            s.query(AiTurn).filter_by(id=turn.id,status='running').update({AiTurn.status:'cancelled',AiTurn.answer:''.join(parts),AiTurn.error:'生成已取消，问题已保留。'})
            s.commit()
