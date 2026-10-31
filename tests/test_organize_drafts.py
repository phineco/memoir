import copy

import pytest
from sqlalchemy import event
from werkzeug.exceptions import HTTPException

import organize_drafts as drafts
import organizing
import organize_preview
from models import Draft, Interview, OrganizeRecord, Person, Quote, TimelineEvent, VerificationItem, get_session
from test_organize_provider import bundle, SOURCE


def setup():
    s = get_session()
    record = organizing.create(s, 'a', 'member-a', {'content': SOURCE, 'subject_id': 'pa', 'narrator_label': '妈妈'})
    record.preview = bundle(); record.preview_revision = 1; record.preview_source_revision = 1
    s.commit(); return record.id


def test_confirm_is_atomic_idempotent_and_never_publishes(app):
    rid = setup(); s = get_session()
    story = drafts.confirm(s, 'a', 'member-a', rid, 1, 1, 'confirm-11', ['pa'])
    sid = story.id
    assert story.author_id == 'member-a' and story.visibility == 'private' and story.publish_status == 'draft'
    assert story.published_at is None
    assert drafts.confirm(s, 'a', 'member-a', rid, 1, 1, 'confirm-22').id == sid
    assert s.query(Draft).filter_by(interview_id=sid).count() == 1
    assert s.query(Quote).filter_by(interview_id=sid).one().text == '慢慢来，总会好的'
    assert s.query(TimelineEvent).filter_by(source_interview_id=sid).one().date_precision == 'year'
    assert s.query(VerificationItem).filter_by(interview_id=sid).one().status == 'pending'
    assert s.get(OrganizeRecord, rid).preview['saved_items']['quotes']
    from ai import family_knowledge
    assert '去县城' not in family_knowledge('a')
    with pytest.raises(HTTPException): drafts.confirm(s, 'a', 'owner-a', rid, 1, 1, 'confirm-33')


def test_invalid_person_or_stale_preview_creates_nothing(app):
    rid = setup(); s = get_session(); before = s.query(Interview).count()
    for version, people in [(0, []), (1, ['pb'])]:
        with pytest.raises(HTTPException): drafts.confirm(s, 'a', 'member-a', rid, 1, version, 'confirm-11', people)
        s.rollback()
        assert s.query(Interview).count() == before and s.get(OrganizeRecord, rid).story_id is None
    s.get(Person, 'pa').del_flag = 1; s.commit()
    with pytest.raises(HTTPException): drafts.confirm(s, 'a', 'member-a', rid, 1, 1, 'confirm-22')


def test_injected_child_failure_rolls_back_entire_story(app):
    rid = setup(); s = get_session(); before = s.query(Interview).count()
    def fail(*args): raise RuntimeError('simulated child write failure')
    event.listen(Quote, 'before_insert', fail)
    try:
        with pytest.raises(RuntimeError): drafts.confirm(s, 'a', 'member-a', rid, 1, 1, 'confirm-11')
    finally:
        event.remove(Quote, 'before_insert', fail)
    assert s.query(Interview).count() == before
    assert s.get(OrganizeRecord, rid).story_id is None
    assert s.query(TimelineEvent).count() == 0
    assert drafts.confirm(s, 'a', 'member-a', rid, 1, 1, 'confirm-11').id


def test_edited_summary_is_not_stored_as_original_quote_and_html_is_escaped(app):
    rid = setup(); s = get_session()
    organize_preview.save(s, 'a', 'member-a', rid, 1, 1, {'title': '核对', 'body': '<script>恶意原稿</script>',
        'keep_quotes_0': 'yes', 'quote_0': '慢慢努力就好'})
    story = drafts.confirm(s, 'a', 'member-a', rid, 1, 2, 'confirm-11')
    assert not s.query(Quote).filter_by(interview_id=story.id).count()
    body = s.query(Draft).filter_by(interview_id=story.id).one().content
    assert '<script>' not in body and '&lt;script&gt;' in body and '摘要（人工整理）' in body
