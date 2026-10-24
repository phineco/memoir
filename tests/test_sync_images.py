from uuid import uuid4

import pytest

from models import Draft, Photo, get_session
from test_sync_revisions import revise


def add_photo(fid='a', deleted=0):
    s = get_session()
    s.add(Photo(id='sync-photo', family_id=fid, title='Synthetic photo', del_flag=deleted))
    s.commit()
    return f'<img src="/f/{fid}/album/sync-photo/image" alt="Memory">'


def test_revision_retains_legal_album_picture_and_removes_unsafe_attributes(client, login):
    image = add_photo()
    login()
    html = '<p>Before</p>' + image.replace('alt=', 'onerror="alert(1)" alt=') + '<p>After</p>'
    assert revise(client, content=html).json['applied']
    draft = get_session().query(Draft).filter_by(interview_id='public-a', is_current=True).one()
    assert image in draft.content and 'onerror' not in draft.content
    assert 'Before' in draft.content and 'After' in draft.content
    assert get_session().get(Draft, 'd-public-a').content == 'content-public-a'


@pytest.mark.parametrize('src', [
    '/f/b/album/sync-photo/image', '/f/a/album/missing/image',
    'https://example.invalid/photo.jpg', 'data:image/png;base64,abc'])
def test_invalid_image_ref_rejects_without_creating_version(client, login, src):
    add_photo('b')
    login()
    response = revise(client, content=f'<p>Text</p><img src="{src}">')
    assert response.status_code == 400 and not response.json['ok']
    assert get_session().get(Draft, 'd-public-a').is_current
    assert get_session().query(Draft).filter_by(interview_id='public-a').count() == 1


def test_removed_photo_preserves_surrounding_text_with_placeholder(client, login):
    image = add_photo(deleted=1)
    login()
    assert revise(client, content='<p>Caption</p>' + image + '<p>After</p>').json['applied']
    content = get_session().query(Draft).filter_by(interview_id='public-a', is_current=True).one().content
    assert '<img' not in content and '照片已移除' in content
    assert 'Caption' in content and 'After' in content


def test_first_import_uses_same_family_image_rules(client, login):
    image = add_photo()
    login()
    response = client.post('/api/sync', json={'family_id': 'a', 'packet': {
        'type': 'interview_upsert', 'clientId': uuid4().hex,
        'payload': {'topic': 'With photo', 'draft': '<p>Text</p>' + image}}})
    assert response.json['applied']
    assert get_session().query(Draft).filter(Draft.content.contains('sync-photo/image')).count() == 1
