"""Check the installable skill artifact, without invoking its workflow."""
from pathlib import Path
import copy
import json
import re
from uuid import uuid4

import pytest
import yaml

from models import (Draft, Interview, NewPerson, Person, PersonIdMap, SyncLog,
                    VerificationItem, WritingPlan, get_session)
from sync_engine import SUPPORTED


ROOT = Path(__file__).resolve().parents[1]
SKILL = ROOT / 'skill/memoir-organizer'


def test_skill_frontmatter_loads_with_standard_yaml_parser():
    text = (SKILL / 'SKILL.md').read_text()
    assert text.startswith('---\n')
    metadata = yaml.safe_load(text.split('---', 2)[1])
    assert metadata['name'] == SKILL.name
    assert isinstance(metadata['description'], str) and metadata['description'].strip()
    assert isinstance(metadata.get('metadata', {}), dict)


def guide_packets():
    text = (SKILL / 'references/sync-guide.md').read_text()
    packets = {}
    for block in re.findall(r'^```json\n(.*?)^```', text, re.M | re.S):
        packet = json.loads(block)
        if packet.get('type') in SUPPORTED:
            packets[packet['type']] = packet
    return packets


@pytest.mark.parametrize('kind', SUPPORTED)
def test_each_documented_packet_runs_against_real_interface(client, login, kind):
    """Templates are executed as written; only clientId and fixture IDs are supplied."""
    packets = guide_packets()
    assert set(packets) == set(SUPPORTED)
    s = get_session()
    s.get(Person, 'pa').name = '王建军'
    s.get(Person, 'pa').aliases = ['三叔']
    s.add_all([
        Person(id='relative-3', family_id='a', name='李桂香'),
        Person(id='relative-1', family_id='a', name='王德顺'),
        PersonIdMap(id='map-2', family_id='a', skill_id='p02', person_id='pa'),
        PersonIdMap(id='map-3', family_id='a', skill_id='p03', person_id='relative-3'),
        Interview(id='guide-original', family_id='a', author_id='owner-a', topic='Original',
                  visibility='public', publish_status='published'),
        Draft(id='guide-original-v1', interview_id='guide-original', version=1, is_current=True, content='Original body'),
        SyncLog(id='guide-original-log', family_id='a', client_id='original-interview-packet',
                op_type='interview_upsert', target_id='guide-original', status='ok'),
        VerificationItem(id='guide-check', interview_id='guide-original', text='1985年是否已在供销社', status='pending'),
        WritingPlan(id='guide-plan', family_id='a', title='Guide plan', status='active', items=json.dumps([
            {'person_id': 'pa', 'person_name': '王建军', 'status': 'pending'},
            {'person_id': 'relative-1', 'person_name': '王德顺', 'status': 'pending'}]))])
    s.commit()
    login()
    packet = copy.deepcopy(packets[kind])
    packet['clientId'] = uuid4().hex
    response = client.post('/api/sync', json={'family_id': 'a', 'packet': packet})
    assert response.status_code == 200, response.json
    assert response.json['applied'] is True
    if kind == 'interview_upsert':
        story = s.query(Interview).filter_by(topic=packet['payload']['topic']).one()
        assert story.person_id == 'pa' and story.narrator_person_id == 'pa'
    elif kind == 'revision_sync':
        assert s.query(Draft).filter_by(interview_id='guide-original', is_current=True).one().version == 2
    elif kind == 'verification_update':
        assert s.get(VerificationItem, 'guide-check').status == 'resolved'
        assert s.get(VerificationItem, 'guide-check').correction == '1983年进供销社'
    elif kind == 'new_person':
        assert s.query(NewPerson).filter_by(name=packet['payload']['name']).count() == 1
    elif kind == 'plan_progress':
        assert [item['status'] for item in json.loads(s.get(WritingPlan, 'guide-plan').items)] == ['doing', 'done']
    else:
        assert s.get(Person, 'pa').status == packet['payload'].get('status', 'drafted')
