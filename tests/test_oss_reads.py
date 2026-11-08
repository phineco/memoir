"""Exercise the real SDK response stream, with network replaced by memory."""
import io
from types import SimpleNamespace

import alibabacloud_oss_v2 as oss
from alibabacloud_oss_v2.io_utils import StreamBodyReader
from alibabacloud_oss_v2.transport.requests_client import _RequestsHttpResponseImpl
import pytest
import requests

from models import Photo,get_session
from storage import OssStorageBackend
from tests.test_album import picture


def sdk_body(data):
    response=requests.Response();response.status_code=200;response.raw=io.BytesIO(data)
    response.headers['Content-Length']=str(len(data))
    return StreamBodyReader(_RequestsHttpResponseImpl(internal_response=response, request=None, block_size=65536))


def backend_for(fetch):
    backend=object.__new__(OssStorageBackend);backend._oss=oss;backend.bucket='synthetic-private-bucket'
    backend.client=SimpleNamespace(get_object=fetch)
    return backend


def test_real_sdk_stream_read_is_bounded_and_closed():
    bodies=[];data=b'picture-data'*100
    def fetch(request):
        body=sdk_body(data);bodies.append(body);return oss.GetObjectResult(body=body)
    backend=backend_for(fetch)
    assert backend.read('album/fake/photo.jpg',25)==data[:25]
    assert bodies[-1].is_closed
    assert backend.read('album/fake/photo.jpg',len(data)+1)==data
    assert bodies[-1].is_closed


def test_read_stops_at_limit_and_closes_on_failure():
    class Stream:
        closed=False
        def iter_bytes(self,**kwargs):
            yield b'123456789'
            raise AssertionError('Must not consume beyond limit')
        def close(self):self.closed=True
    body=Stream();backend=backend_for(lambda request:oss.GetObjectResult(body=body))
    assert backend.read('fake',5)==b'12345' and body.closed
    class Broken(Stream):
        def iter_bytes(self,**kwargs):raise OSError('synthetic read failure');yield
    broken=Broken();backend=backend_for(lambda request:oss.GetObjectResult(body=broken))
    with pytest.raises(OSError):backend.read('fake',5)
    assert broken.closed


def test_album_pages_serve_sdk_images_and_keep_family_access(client,login,monkeypatch):
    data=picture();bodies=[];reads=[];missing_thumb=[False]
    def fetch(request):
        reads.append(request.key)
        if missing_thumb[0] and request.key.endswith('-thumb.jpg'):raise FileNotFoundError('missing thumbnail')
        body=sdk_body(data);bodies.append(body);return oss.GetObjectResult(body=body)
    monkeypatch.setattr('storage._backend',backend_for(fetch))
    s=get_session();s.add(Photo(id='oss-photo',family_id='a',storage_path='album/a/oss-photo.jpg',uploaded_by='owner-a',title='SDK photo'));s.commit()
    login()
    assert '/f/a/album/oss-photo/image?size=thumb' in client.get('/f/a/album').get_data(as_text=True)
    assert '/f/a/album/oss-photo/image' in client.get('/f/a/album/oss-photo/edit').get_data(as_text=True)
    for suffix in ['', '?size=thumb']:
        result=client.get('/f/a/album/oss-photo/image'+suffix)
        assert result.status_code==200 and result.data==data
        assert result.mimetype=='image/jpeg' and result.headers['Cache-Control']=='private, no-store'
    missing_thumb[0]=True
    fallback=client.get('/f/a/album/oss-photo/image?size=thumb')
    assert fallback.status_code==200 and fallback.data==data
    assert all(body.is_closed for body in bodies)
    count=len(reads);login('owner-b')
    assert client.get('/f/a/album/oss-photo/image').status_code==404 and len(reads)==count
