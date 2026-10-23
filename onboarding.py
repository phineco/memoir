"""Optional role-aware guidance; no identity claim or person is needed to write."""
import hashlib
import datetime

from sqlalchemy import or_
from sqlalchemy.exc import IntegrityError

from models import FamilyMember,FamilyVisit,Interview,Invite,Person,User,get_session
from reporting import local_now


def touch(family_id,user_id):
    s=get_session();query=s.query(FamilyVisit).filter_by(family_id=family_id,user_id=user_id)
    row=query.first()
    if row:return row
    eligible=s.query(Interview.id).filter_by(family_id=family_id,author_id=user_id).first() is None
    try:
        with s.begin_nested():
            row=FamilyVisit(id=hashlib.sha256((family_id+'\0'+user_id).encode()).hexdigest(),family_id=family_id,
                user_id=user_id,first_seen_at=local_now(),cohort_eligible=eligible,guide_status='auto',create_by=user_id)
            s.add(row);s.flush()
    except IntegrityError:
        row=query.with_for_update().populate_existing().one()
    return row


def record(family_id,user_id,action):
    field={'read':FamilyVisit.first_read_at,'saved':FamilyVisit.first_saved_at,'published':FamilyVisit.first_published_at}[action]
    touch(family_id,user_id)
    return get_session().query(FamilyVisit).filter(FamilyVisit.family_id==family_id,FamilyVisit.user_id==user_id,field.is_(None)).update({field:local_now()},synchronize_session=False)


def guide(family_id,user_id,is_admin):
    s=get_session();visit=touch(family_id,user_id)
    if visit.guide_status=='hidden':return None
    claimed=s.query(Person.id).filter_by(family_id=family_id,user_id=user_id,del_flag=0).first() is not None
    own=s.query(Interview.id).filter_by(family_id=family_id,author_id=user_id,del_flag=0)
    written=own.first() is not None
    published=own.filter(or_(Interview.publish_status=='published',Interview.publish_status.is_(None))).first() is not None
    has_people=s.query(Person.id).filter_by(family_id=family_id,del_flag=0).first() is not None
    joined=s.query(FamilyMember.id).join(User,FamilyMember.user_id==User.id).filter(
        FamilyMember.family_id==family_id,FamilyMember.user_id!=user_id,FamilyMember.del_flag==0,
        FamilyMember.role.in_(('owner','admin','member')),User.del_flag==0).first() is not None
    invited=s.query(Invite.id).filter(Invite.family_id==family_id,Invite.del_flag==0,
        or_(Invite.expire_at.is_(None),Invite.expire_at>datetime.datetime.now()),
        or_(Invite.max_uses.is_(None),Invite.max_uses==0,Invite.used_count.is_(None),Invite.used_count<Invite.max_uses)).first() is not None
    done=[written,published,joined] if is_admin else [bool(visit.first_read_at),written,published]
    if all(done) and visit.guide_status!='show':return None
    return dict(admin=is_admin,has_people=has_people,invited=invited,joined=joined,published=published,written=written,claimed=claimed,
                read=bool(visit.first_read_at),completed=sum(done),total=3)
