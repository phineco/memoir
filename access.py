"""家庭和故事访问策略；public 始终表示家庭内可见。"""
from models import Family, FamilyMember, InterviewViewer


def family_role(s, family_id, user_id):
    if not user_id:
        return None
    fam = s.query(Family).filter_by(id=family_id, del_flag=0).first()
    if not fam:
        return None
    member = s.query(FamilyMember).filter_by(
        family_id=family_id, user_id=user_id).first()
    if member is not None:
        return member.role if member.del_flag == 0 and member.role in (
            "owner", "admin", "member") else None
    # 仅兼容尚未生成成员记录的旧创建者；被移除的成员不能借此恢复权限。
    return "owner" if fam.owner_user_id == user_id else None


def story_visible(s, story, user_id, include_drafts=True):
    if story.del_flag != 0 or not family_role(s, story.family_id, user_id):
        return False
    if (story.publish_status or "published") != "published":
        return include_drafts and story.author_id == user_id
    if story.author_id == user_id or (story.visibility or "public") == "public":
        return True
    if story.visibility == "specific":
        return s.query(InterviewViewer).filter_by(
            interview_id=story.id, user_id=user_id, del_flag=0).first() is not None
    return False
