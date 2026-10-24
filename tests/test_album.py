import io
import re
import sqlite3
from pathlib import Path

import pytest
from PIL import Image

from migrate import run_migrations
from models import Photo,Draft,Interview,FamilyMember,get_session
from storage import LocalStorageBackend


def picture():
    result=io.BytesIO();image=Image.new('RGB',(100,60),'green')
    exif=Image.Exif();exif[270]='private camera comment';exif[274]=6
    image.save(result,'JPEG',exif=exif)
    return result.getvalue()


@pytest.fixture
def store(app,monkeypatch):
    backend=LocalStorageBackend(app.config['UPLOAD_DIR'])
    monkeypatch.setattr('storage._backend',backend)
    return backend


def token(client,path='/f/a/album/upload'):
    response=client.get(path);assert response.status_code==200
    return re.search(r'name="csrf_token" value="([^"]+)"',response.get_data(as_text=True))[1]


def upload(client,csrf,**values):
    data=dict(csrf_token=csrf,title='老院子合影',caption='一家人的夏日',location='合肥老家',time_precision='day',photo_year='1985',photo_month='6',photo_day='12',photo=(io.BytesIO(picture()),'phone.jpeg'))
    data.update(values)
    return client.post('/f/a/album/upload',data=data)


def photo():return get_session().query(Photo).one()


def test_upload_timeline_location_and_private_image(store,app,client,login):
    login('member-a');csrf=token(client);response=upload(client,csrf)
    assert response.status_code==302
    p=photo();assert (p.photo_year,p.photo_month,p.photo_day,p.location)==(1985,6,12,'合肥老家')
    assert p.uploaded_by=='member-a' and p.person_id is None
    image='/f/a/album/'+p.id+'/image'
    output=client.get(image);assert output.status_code==200 and output.mimetype=='image/jpeg'
    assert output.headers['Cache-Control']=='private, no-store' and output.headers['X-Content-Type-Options']=='nosniff'
    with Image.open(io.BytesIO(output.data)) as decoded:
        assert decoded.size==(60,100) and not decoded.getexif()
    body=client.get('/f/a/album?location=合肥').get_data(as_text=True)
    assert '老院子合影' in body and '1985年6月12日' in body
    assert not client.get('/f/a/album/choices?location=苏州').json['photos']
    assert client.get('/f/a/album/choices?location=%25').json['total']==0
    assert client.get(image+'?size=thumb').status_code==200
    login('owner-b');assert client.get(image).status_code==404
    assert client.get('/f/a/album/choices').status_code==404
    login('member-a');get_session().get(FamilyMember,'member').del_flag=1;get_session().commit()
    assert client.get(image).status_code==404


@pytest.mark.parametrize('values',[
    {'title':'','caption':''},{'location':''},{'location':'x'*256},{'title':'x'*121},{'caption':'x'*256},
    {'time_precision':''},{'photo_month':'13'},{'photo_day':'31'}, {'photo_year':'0'},{'person_id':'pb'},
    {'photo':(io.BytesIO(b'\x89PNG\r\n\x1a\nnot an image'),'fake.png')},
    {'photo':(io.BytesIO(b'<svg onload="alert(1)"/>'),'bad.svg')},
])
def test_metadata_and_image_validation_writes_nothing(store,client,login,values):
    login();response=upload(client,token(client),**values)
    assert response.status_code==400 and get_session().query(Photo).count()==0
    assert not Path(store.upload_dir).exists()


@pytest.mark.parametrize('precision,year,month,day', [('year',1985,None,None),('month',1985,6,None),('unknown',None,None,None)])
def test_partial_dates_do_not_invent_missing_parts(store,client,login,precision,year,month,day):
    login();assert upload(client,token(client),time_precision=precision).status_code==302
    p=photo();assert (p.photo_year,p.photo_month,p.photo_day)==(year,month,day)


def test_timeline_null_last_pagination_and_legacy_person_photos(store,client,login):
    s=get_session()
    for i in range(26):s.add(Photo(id=f'p{i:02}',family_id='a',person_id='pa',photo_year=1980+i if i<25 else None,location='老家',caption='旧照片'))
    s.add(Photo(id='foreign',family_id='b',photo_year=2026,location='老家',caption='别家'))
    s.commit();login();data=client.get('/f/a/album/choices').json
    assert (data['total'],data['pages'],data['photos'][0]['id'])==(26,2,'p24')
    tail=client.get('/f/a/album/choices?page=2').json['photos']
    assert tail[-1]['id']=='p25' and tail[-1]['date']=='拍摄时间不详'
    assert '家庭相册' in client.get('/f/a/more').get_data(as_text=True)
    assert client.get('/f/a/album?page=0').status_code==400
    assert client.get('/f/a/album?page=3').status_code==404
    assert client.get('/f/a/album/choices?photo_id=foreign').status_code==404


def test_edit_delete_roles_csrf_and_stale_metadata(store,client,login):
    login('member-a');csrf=token(client);upload(client,csrf);pid=photo().id
    path='/f/a/album/'+pid
    assert client.post(path+'/edit',data={'title':'CSRF'}).status_code==400
    version=str(photo().metadata_version);data=dict(csrf_token=csrf,base_version=version,title='更新的名称',location='苏州',time_precision='unknown')
    assert client.post(path+'/edit',data=data).status_code==302
    assert client.post(path+'/edit',data=data).status_code==409
    assert photo().photo_year is None and photo().location=='苏州'
    login('owner-a');csrf=token(client)
    # The owner can manage another member's photo; edit still requires metadata.
    assert client.get(path+'/edit').status_code==200
    assert client.post(path+'/delete',data={'csrf_token':csrf}).status_code==302
    assert client.get(path+'/image').status_code==404 and client.get(path).status_code==404
    assert not list(Path(store.upload_dir).rglob('*.jpg'))


def test_ordinary_member_cannot_manage_others_photo(store,client,login):
    login();upload(client,token(client));pid=photo().id
    login('member-a');csrf=token(client)
    assert client.get('/f/a/album/'+pid+'/edit').status_code==403
    assert client.post('/f/a/album/'+pid+'/delete',data={'csrf_token':csrf}).status_code==403
    assert client.get('/f/a/album/'+pid+'/image').status_code==200


def test_embedding_survives_save_revision_and_removal_without_external_images(store,client,login):
    login();upload(client,token(client));pid=photo().id;src='/f/a/album/'+pid+'/image'
    html=f'<p>文字不变</p><p><img src="{src}" alt="老院子" onerror="alert(1)"></p>'
    response=client.post('/f/a/write',data=dict(topic='看图说故事',content=html,action='publish',visibility='private'))
    assert response.status_code==302
    iv=get_session().query(Interview).filter_by(topic='看图说故事').one();draft=get_session().query(Draft).filter_by(interview_id=iv.id).one()
    assert src in draft.content and 'onerror' not in draft.content
    assert f'src="{src}"' in client.get(response.location).get_data(as_text=True)
    login('member-a');assert client.get(response.location).status_code==404
    # Album sharing is deliberately independent of the story visibility.
    assert client.get(src).status_code==200
    login();csrf=token(client);edit='/f/a/story/'+iv.id+'/edit'
    response=client.post(edit,data=dict(topic='看图说故事',content=html,base_version='1',revision_reason='保留照片'))
    assert response.status_code==302
    assert src in client.get('/f/a/story/'+iv.id+'/history').get_data(as_text=True)
    assert client.post('/f/a/album/'+pid+'/delete',data={'csrf_token':csrf}).status_code==302
    body=client.get('/f/a/story/'+iv.id).get_data(as_text=True)
    assert '照片已移除或不可用' in body and f'src="{src}"' not in body and '文字不变' in body


@pytest.mark.parametrize('src',['https://example.com/track.png','data:image/png;base64,AAAA','/f/b/album/foreign/image','/f/a/album/missing/image'])
def test_forged_story_images_are_rejected(store,client,login,src):
    login();response=client.post('/f/a/write',data=dict(topic='forged',content=f'<p><img src="{src}"></p>',action='publish'))
    assert response.status_code==400
    assert not get_session().query(Interview).filter_by(topic='forged').count()


def test_missing_thumbnail_falls_back_and_object_failure_revokes_access(store,client,login,monkeypatch):
    login();csrf=token(client);upload(client,csrf);p=photo();src='/f/a/album/'+p.id+'/image'
    from album import thumb_key
    store.delete(thumb_key(p.storage_path))
    assert client.get(src+'?size=thumb').status_code==200
    monkeypatch.setattr(store,'delete',lambda key:(_ for _ in ()).throw(RuntimeError('storage unavailable')))
    assert client.post('/f/a/album/'+p.id+'/delete',data={'csrf_token':csrf}).status_code==302
    assert client.get(src).status_code==404


def test_migration_preserves_legacy_year_and_repeats_safely(tmp_path):
    path=tmp_path/'old.db'
    with sqlite3.connect(path) as conn:
        conn.execute('CREATE TABLE photos (id TEXT,family_id TEXT,del_flag INT,photo_year INT)')
        conn.execute("INSERT INTO photos VALUES ('old','a',0,1985)")
    migrations=tmp_path/'migrations';migrations.mkdir()
    source=Path(__file__).resolve().parents[1]/'migrations/014_family_album.sql'
    (migrations/source.name).write_bytes(source.read_bytes())
    url='sqlite:///'+str(path);before=path.read_bytes();run_migrations(url,dry_run=True,migrations_dir=migrations)
    assert path.read_bytes()==before
    run_migrations(url,migrations_dir=migrations);run_migrations(url,migrations_dir=migrations)
    with sqlite3.connect(path) as conn:
        assert conn.execute('SELECT photo_year,photo_month,photo_day,title,location FROM photos').fetchone()==(1985,None,None,None,None)


def test_object_proxy_never_returns_an_oss_url(client,login,monkeypatch):
    data=picture();reads=[]
    class PrivateStore:
        def read(self,key,limit):reads.append(key);return data
        def url(self,key):raise AssertionError('No signed browser URLs for album media')
    monkeypatch.setattr('storage._backend',PrivateStore())
    s=get_session();s.add(Photo(id='private',family_id='a',storage_path='album/a/abc.jpg',title='Private object'));s.commit()
    login();response=client.get('/f/a/album/private/image')
    assert response.status_code==200 and response.data==data and reads==['album/a/abc.jpg']
    body=client.get('/f/a/album').get_data(as_text=True)
    assert 'oss-' not in body and '/f/a/album/private/image?size=thumb' in body
    login('owner-b');assert client.get('/f/a/album/private/image').status_code==404 and len(reads)==1


def test_upload_csrf_size_and_storage_failure_are_recoverable(store,app,client,login,monkeypatch):
    login();csrf=token(client)
    assert upload(client,'invalid-csrf').status_code==400
    assert upload(client,csrf,photo=(io.BytesIO(b'x'*(10*1024*1024+1)),'large.jpg')).status_code==400
    def fail(data,key):raise RuntimeError('private-storage-error')
    monkeypatch.setattr(store,'save',fail)
    result=upload(client,csrf)
    assert result.status_code==503 and '照片暂未保存' in result.get_data(as_text=True)
    assert 'private-storage-error' not in result.get_data(as_text=True) and get_session().query(Photo).count()==0


def test_deleted_photo_does_not_block_later_story_text_edits(store,client,login):
    login();csrf=token(client);upload(client,csrf);pid=photo().id
    image=f'<img src="/f/a/album/{pid}/image" alt="old">'
    client.post('/f/a/album/'+pid+'/delete',data={'csrf_token':csrf})
    response=client.post('/f/a/story/public-a/edit',data=dict(topic='Continued',content='<p>New text</p>'+image,base_version='1',revision_reason='After photo removal'))
    assert response.status_code==302
    draft=get_session().query(Draft).filter_by(interview_id='public-a',is_current=True).one()
    assert 'New text' in draft.content and '照片已移除或不可用' in draft.content and '<img' not in draft.content


def test_person_photo_entry_reuses_required_metadata_and_private_images(store,client,login):
    login();csrf=token(client)
    data=dict(csrf_token=csrf,title='Person portrait',location='Old home',time_precision='year',photo_year='1980',photo2=(io.BytesIO(picture()),'phone.jpg'))
    assert client.post('/f/a/person/pa/photos/upload',data=data).status_code==302
    p=photo();assert p.person_id=='pa'
    body=client.get('/f/a/person/pa').get_data(as_text=True)
    assert '/f/a/album/'+p.id+'/image?size=thumb' in body and 'Person portrait' in body
    assert client.post('/f/a/person/pa/photos/'+p.id+'/delete',data={}).status_code==400
