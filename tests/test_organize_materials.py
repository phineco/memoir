import pytest
from werkzeug.exceptions import HTTPException

import organizing
from models import FamilyMember, OrganizeRecord, OrganizeSource, get_session


def test_material_versions_private_and_independent_of_stories(app):
    s = get_session()
    record = organizing.create(s, 'a', 'member-a', {'content': '小时候住在山边。'})
    rid = record.id
    assert organizing.owned(s, 'a', 'member-a', rid).content == '小时候住在山边。'
    for fid, uid in [('a', 'owner-a'), ('b', 'owner-b'), ('a', 'outsider')]:
        with pytest.raises(HTTPException) as error:
            organizing.owned(s, fid, uid, rid)
        assert error.value.code == 404
    organizing.update(s, 'a', 'member-a', rid, 1, {'content': '小时候住在河边。'})
    assert [r.content for r in s.query(OrganizeSource).filter_by(record_id=rid).order_by(OrganizeSource.revision)] == ['小时候住在山边。', '小时候住在河边。']
    with pytest.raises(HTTPException) as error:
        organizing.update(s, 'a', 'member-a', rid, 1, {'content': 'Stale'})
    assert error.value.code == 409
    assert s.get(OrganizeRecord, rid).content == '小时候住在河边。'
    organizing.delete(s, 'a', 'member-a', rid)
    assert not s.query(OrganizeSource).filter_by(record_id=rid).count()
    assert s.get(OrganizeRecord,rid).del_flag==1 and s.get(OrganizeRecord,rid).content==''


def test_removed_member_and_cross_family_person_rejected(app):
    s = get_session()
    with pytest.raises(HTTPException):
        organizing.create(s, 'a', 'member-a', {'content': 'Body', 'subject_id': 'pb'})
    record = organizing.create(s, 'a', 'member-a', {'content': 'Body'})
    s.get(FamilyMember, 'member').del_flag = 1
    s.commit()
    with pytest.raises(HTTPException):
        organizing.owned(s, 'a', 'member-a', record.id)


def test_input_limit_never_truncates(app):
    with pytest.raises(HTTPException):
        organizing.create(get_session(), 'a', 'member-a', {'content': '字' * 20001})
    assert get_session().query(OrganizeRecord).count() == 0


def test_deleted_nonce_cannot_resurrect_raw_content(app):
    s=get_session();data={'content':'需要删除的私有原文','narrator_label':'私有讲述称谓'}
    rid=organizing.create(s,'a','member-a',data,nonce='source-delete').id
    organizing.delete(s,'a','member-a',rid)
    organizing.delete(s,'a','member-a',rid)  # repeated delete remains harmless
    with pytest.raises(HTTPException) as error:organizing.create(s,'a','member-a',data,nonce='source-delete')
    assert error.value.code==409;s.rollback()
    row=s.get(OrganizeRecord,rid)
    assert row.del_flag and not row.content and row.narrator_label is None and row.preview is None
    assert not s.query(OrganizeSource).filter_by(record_id=rid).count()
    with pytest.raises(HTTPException):organizing.owned(s,'a','member-a',rid)
