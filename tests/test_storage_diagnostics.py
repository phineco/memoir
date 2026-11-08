import json

from alibabacloud_oss_v2 import exceptions as errors
from storage_diagnostics import storage_error_details
from tests.test_album import upload,token
from models import get_session,Photo


def service(**overrides):
    values=dict(status_code=403,code='AccessDenied',request_id='ABC123',message='SECRET',ec='0003-00000001',timestamp='SECRET',request_target='https://SECRET')
    values.update(overrides);return errors.ServiceError(**values)


def test_service_fields_and_nested_transport_errors():
    error=errors.OperationError(name='PutObject',error=service())
    details=storage_error_details(error)
    assert details==dict(oss_status_code=403,oss_code='AccessDenied',oss_request_id='ABC123',oss_ec='0003-00000001',storage_error_chain=['OperationError','ServiceError'])
    assert 'SECRET' not in json.dumps(details)
    assert storage_error_details(errors.OperationError(name='PutObject',error=errors.RequestError(error=TimeoutError('SECRET'))))['storage_error_chain']==['OperationError','RequestError','TimeoutError']
    assert storage_error_details(RuntimeError('SECRET'))=={}
    assert storage_error_details(errors.OperationError(name='PutObject',error=service(status_code='403',code='https://SECRET',request_id='SECRET\nURL',ec='SECRET')))==dict(storage_error_chain=['OperationError','ServiceError'])


def test_cycles_are_bounded():
    error=errors.OperationError(name='PutObject',error=ValueError('SECRET'));error._error=error
    assert storage_error_details(error)['storage_error_chain']==['OperationError']


def test_upload_reports_safe_provider_fields(app,client,login,monkeypatch,caplog):
    login();csrf=token(client)
    class Backend:
        def save(self,*args):raise errors.OperationError(name='PutObject',error=service())
    monkeypatch.setattr('album.get_storage',lambda:Backend())
    result=upload(client,csrf)
    assert result.status_code==503 and get_session().query(Photo).count()==0
    events=[json.loads(r.message) for r in caplog.records if r.message.startswith('{')]
    failure=next(e for e in events if e.get('kind')=='album_storage')
    assert failure['oss_code']=='AccessDenied' and failure['oss_status_code']==403
    assert failure['request_id']==result.headers['X-Request-ID']
    assert 'SECRET' not in caplog.text and 'SECRET' not in result.get_data(as_text=True)
