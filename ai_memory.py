"""Reset boundaries protect against old history and concurrent memory resurrection."""
import hashlib
import uuid

from sqlalchemy.exc import IntegrityError

from access import family_role
from models import AiMemory, AiPreference, AiTurn, get_session


def preference(family_id,user_id,lock=False,create=False):
    s=get_session()
    query=s.query(AiPreference).filter_by(family_id=family_id,user_id=user_id)
    if create and query.first() is None:
        try:
            with s.begin_nested():
                s.add(AiPreference(id=hashlib.sha256((family_id+'\0'+user_id).encode()).hexdigest(),
                                   family_id=family_id,user_id=user_id,epoch='legacy',create_by=user_id))
                s.flush()
        except IntegrityError:pass
    if lock:query=query.with_for_update()
    return query.populate_existing().first()


def context_stamp(family_id,user_id):
    import ai
    base=ai.context_stamp(family_id)
    pref=preference(family_id,user_id)
    return stamp_for_epoch(base,pref.epoch if pref else 'legacy')


def stamp_for_epoch(base,epoch):
    if epoch=='legacy':return base
    return 'usr1:'+hashlib.sha256((base+epoch).encode()).hexdigest()[:24]


def guard_write(family_id,user_id,expected):
    """Caller must commit while holding this preference row lock."""
    s=get_session()
    pref=preference(family_id,user_id,lock=True,create=True)
    import ai
    # Use the locking read's epoch, never overwrite it with a repeatable-read snapshot.
    if not family_role(s,family_id,user_id) or stamp_for_epoch(ai.context_stamp(family_id),pref.epoch)!=expected:
        s.rollback()
        return False
    return True


def reset(family_id,user_id):
    s=get_session()
    if not family_role(s,family_id,user_id):raise ValueError('无权访问')
    pref=preference(family_id,user_id,lock=True,create=True)
    pref.epoch=uuid.uuid4().hex
    pref.update_by=user_id
    s.query(AiMemory).filter_by(family_id=family_id,user_id=user_id).update({AiMemory.del_flag:1,AiMemory.content:None})
    s.query(AiTurn).filter_by(family_id=family_id,user_id=user_id,status='running').update(
        {AiTurn.status:'cancelled',AiTurn.error:'AI 记忆已重置，请重新提问。'})
    s.commit()
