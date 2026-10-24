"""Version preconditions and atomic draft claims shared by web and sync writes."""
from sqlalchemy import func

from models import Draft, new_id
from reporting import local_now


class RevisionConflict(ValueError):
    pass


def append_revision(s, story, user_id, content, base_version, reason):
    if isinstance(base_version, bool) or not str(base_version).isdigit():
        raise RevisionConflict("全文修订必须提供 base_version，请先在网页核对当前版本")
    reason = (reason or '').strip()
    if not reason:
        raise ValueError("请填写 revision_reason（本次修订原因）")
    current = s.query(Draft).filter_by(
        interview_id=story.id, is_current=True, del_flag=0).with_for_update().populate_existing().first()
    if int(base_version) != (current.version if current else 0):
        raise RevisionConflict("故事已更新，请核对当前正文后重新修订，不能覆盖较新版本")
    if current:
        claimed = s.query(Draft).filter_by(id=current.id, is_current=True).update(
            {Draft.is_current: False}, synchronize_session=False)
        if claimed != 1:
            raise RevisionConflict("故事刚刚被其他窗口修改，请核对当前正文后重试")
        current.is_current = False
    maximum = s.query(func.max(Draft.version)).filter_by(interview_id=story.id).scalar() or 0
    draft = Draft(id=new_id(), interview_id=story.id, version=maximum + 1,
                  is_current=True, content=content, create_by=user_id,
                  remarks=reason[:255], create_date=local_now())
    s.add(draft)
    story.update_by, story.update_date = user_id, local_now()
    return draft
