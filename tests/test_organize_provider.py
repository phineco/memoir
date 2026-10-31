import copy
import json

import pytest
import requests

from organize_provider import GenerationError, generate, validate

SOURCE = '1980年，我跟妈妈去了县城。她说：慢慢来，总会好的。我不确定是春天还是秋天。'


def bundle():
    return dict(title='去县城', body=SOURCE, quotes=[{'text': '慢慢来，总会好的', 'evidence': '她说：慢慢来，总会好的。'}],
        verification=[{'text': '是春天还是秋天？', 'evidence': '我不确定是春天还是秋天。'}],
        timeline=[{'date': '1980', 'precision': 'year', 'title': '去县城', 'evidence': '1980年，我跟妈妈去了县城。'}],
        people=[{'name': '妈妈', 'context': '陪我去县城', 'evidence': '我跟妈妈去了县城。'}], period=None)


def test_grounded_extractions_keep_uncertainty_and_reject_invented_evidence():
    assert validate(bundle(), SOURCE) == bundle()
    for change in ('quote', 'evidence', 'date', 'identity', 'html_command', 'period'):
        data = copy.deepcopy(bundle())
        if change == 'quote': data['quotes'][0]['text'] = '原文没有说过'
        if change == 'evidence': data['verification'][0]['evidence'] = '另外一个故事'
        if change == 'date': data['timeline'][0]['date'] = '1981'
        if change == 'identity': data['people'][0]['person_id'] = 'pb'
        if change == 'html_command': data['visibility'] = 'public'
        if change == 'period': data['period'] = {'start': '1980', 'end': '1981', 'precision': 'year', 'evidence': SOURCE}
        with pytest.raises(GenerationError): validate(data, SOURCE)


class Response:
    status_code = 200
    def __init__(self, content, finish='stop'):
        self.blob = {'choices': [{'finish_reason': finish, 'message': {'content': content}}], 'usage': {'total_tokens': 10, 'unsafe': 'secret'}}
        self.closed = False
    def iter_content(self, size):
        yield json.dumps(self.blob, ensure_ascii=False).encode()
    def close(self): self.closed = True


def test_single_format_repair_recorded_and_no_family_context(app, monkeypatch):
    responses = [Response('{"bad":1}'), Response(json.dumps(bundle()))]
    calls = []
    def post(*args, **kwargs):
        calls.append(copy.deepcopy(kwargs['json']))
        return responses[len(calls)-1]
    monkeypatch.setattr(requests, 'post', post)
    with app.app_context():
        out, usage = generate({'content': SOURCE, 'identity': {'narrator_label': '妈妈'}, 'model': 'configured-model'})
    assert out['title'] == '去县城' and len(calls) == 2
    assert usage == {'calls': [{'total_tokens': 10}, {'total_tokens': 10}]}
    assert all(r.closed for r in responses)
    assert calls[0]['model'] == 'configured-model'
    assert 'family_knowledge' not in str(calls)


@pytest.mark.parametrize('mode', ['timeout', 'truncated', 'invalid-twice'])
def test_no_blind_retry_after_uncertain_or_truncated_call(app, monkeypatch, mode):
    calls = []
    def post(*args, **kwargs):
        calls.append(1)
        if mode == 'timeout': raise requests.ReadTimeout('secret input')
        return Response('{}', 'length' if mode == 'truncated' else 'stop')
    monkeypatch.setattr(requests, 'post', post)
    with app.app_context(), pytest.raises(GenerationError) as error:
        generate({'content': SOURCE, 'identity': {}, 'model': 'test'})
    assert len(calls) == (2 if mode == 'invalid-twice' else 1)
    assert error.value.uncertain == (mode == 'timeout')
    assert 'secret' not in str(error.value)


def test_cancelled_between_complete_reply_and_format_repair_stops_second_call(app,monkeypatch):
    calls=[]
    def post(*args,**kwargs):calls.append(1);return Response('{}')
    def cancelled():raise GenerationError('cancelled')
    monkeypatch.setattr(requests,'post',post)
    with app.app_context(),pytest.raises(GenerationError):
        generate({'content':SOURCE,'identity':{},'model':'test','dispatch_check':cancelled})
    assert len(calls)==1
