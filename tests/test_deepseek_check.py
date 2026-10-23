import io
import json
from types import SimpleNamespace
import urllib.error

from deepseek_check import run_check


def settings():
    return SimpleNamespace(DEEPSEEK_API_KEY='DO-NOT-PRINT-SECRET',DEEPSEEK_BASE_URL='https://custom.example.test/v1',DEEPSEEK_MODEL='configured-model')


def test_check_uses_application_configuration_without_printing_key(capsys):
    requests=[]
    def opener(request,timeout):
        requests.append(request)
        return io.BytesIO(json.dumps({'data':[{'id':'configured-model'}]} if len(requests)==1 else {'choices':[{'message':{'content':'ok'}}]}).encode())
    assert run_check(settings(),True,opener)==0
    assert requests[0].full_url=='https://custom.example.test/v1/models'
    assert json.loads(requests[1].data)['model']=='configured-model'
    assert 'DO-NOT-PRINT' not in capsys.readouterr().out


def test_rate_limit_is_failure_and_does_not_echo_provider_body(capsys):
    def opener(request,timeout):raise urllib.error.HTTPError(request.full_url,429,'PRIVATE_BODY',{},None)
    assert run_check(settings(),True,opener)==2
    assert 'PRIVATE_BODY' not in capsys.readouterr().out
