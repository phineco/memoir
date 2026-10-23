import json
import re

from models import Interview, Person, get_session


def test_companion_is_the_author_not_the_narrator(client, login):
    login('member-a')
    s = get_session()
    s.add(Person(id='my-person', family_id='a', name='记录人自己', user_id='member-a'))
    s.commit()
    html = client.get('/f/a/write?mode=accompany').get_data(as_text=True)
    assert 'value="accompany" checked' in html
    assert 'value="my-person" selected' not in html
    response = client.post('/f/a/write', data={
        'recording_mode':'accompany', 'topic':'家人讲的回忆', 'content':'<p>保留讲述者说的话。</p>',
        'narrator_person_id':'pa', 'subject_id':'pa', 'action':'draft', 'visibility':'private'})
    assert response.status_code == 302
    story = get_session().query(Interview).filter_by(topic='家人讲的回忆').one()
    assert story.author_id == 'member-a' and story.narrator_person_id == 'pa'
    assert story.visibility == 'private' and story.publish_status == 'draft'


def test_empty_narrator_is_not_replaced_with_the_recording_child(client, login):
    login('member-a')
    s = get_session()
    s.add(Person(id='my-person', family_id='a', name='记录人自己', user_id='member-a'))
    s.commit()
    for mode in ('self', 'accompany'):
        assert client.post('/f/a/write', data={
            'recording_mode':mode, 'topic':mode, 'content':'<p>还没确认是谁讲的。</p>',
            'narrator_person_id':'', 'action':'draft'}).status_code == 302
        story = get_session().query(Interview).filter_by(topic=mode).one()
        assert story.narrator_person_id is None
    assert client.post('/f/a/write', data={
        'recording_mode':'accompany', 'topic':'晚些补人物', 'content':'<p>先存下来。</p>',
        'action':'draft'}).status_code == 302
    assert get_session().query(Interview).filter_by(topic='晚些补人物').one().narrator_person_id is None


def test_validation_keeps_companion_selection_and_original_content(client, login):
    login('member-a')
    response = client.post('/f/a/write', data={
        'recording_mode':'accompany', 'topic':'', 'content':'<p>已经输入的回忆。</p>',
        'narrator_person_id':'pa', 'writing_prompt':'home', 'action':'draft'})
    html = response.get_data(as_text=True)
    assert 'value="accompany" checked' in html and 'value="pa" selected' in html
    assert json.loads(re.search(r'const initialContent = (.*);', html).group(1)) == '<p>已经输入的回忆。</p>'
    assert get_session().query(Interview).filter_by(author_id='member-a').count() == 0
    assert client.post('/f/a/write', data={'recording_mode':'someone-else'}).status_code == 400
