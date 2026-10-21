import datetime
import struct

import pytest

from invite_links import public_base_url, qr_png
from models import FamilyMember, Invite, get_session


def add_invite(**overrides):
    data=dict(id='qr-a',family_id='a',code='test-invite-a',max_uses=2,used_count=0,
              expire_at=datetime.datetime.now()+datetime.timedelta(days=1))
    data.update(overrides)
    inv=Invite(**data)
    get_session().add(inv);get_session().commit()
    return data['id']


def test_invite_generation_uses_public_domain_behind_proxy(client,login):
    with client.session_transaction(base_url='http://127.0.0.1:443') as session:
        session['user_id']='owner-a'
    response=client.post('/f/a/invites/create',data={'days':'7','max_uses':'3'},
                         base_url='http://127.0.0.1:443',
                         headers={'X-Forwarded-Host':'untrusted.example','X-Forwarded-Proto':'http'})
    assert response.status_code==302
    inv=get_session().query(Invite).one()
    code=inv.code
    html=client.get(response.location,base_url='http://127.0.0.1:443').get_data(as_text=True)
    assert 'https://family.scyllatech.cn/join/'+code in html
    assert '127.0.0.1:443/join/' not in html and 'untrusted.example' not in html
    assert f'/f/a/invites/{inv.id}/qr.png' in html
    assert '下载二维码（PNG）' in html


def test_existing_invites_and_old_session_urls_are_rebuilt(client,login):
    add_invite()
    login()
    with client.session_transaction() as session:
        session['new_invite']={'code':'test-invite-a','url':'http://127.0.0.1:443/join/test-invite-a'}
    html=client.get('/f/a/manage').get_data(as_text=True)
    assert html.count('https://family.scyllatech.cn/join/test-invite-a') >= 2
    assert '127.0.0.1' not in html
    html=client.get('/f/a/manage').get_data(as_text=True)
    assert 'https://family.scyllatech.cn/join/test-invite-a' in html
    assert '/f/a/invites/qr-a/qr.png' in html


def test_qr_png_download_is_read_only_and_encodes_same_public_url(client,login):
    add_invite()
    login()
    members_before=get_session().query(FamilyMember).count()
    preview=client.get('/f/a/invites/qr-a/qr.png')
    download=client.get('/f/a/invites/qr-a/qr.png?download=1')
    assert preview.status_code==download.status_code==200
    assert preview.mimetype=='image/png'
    assert preview.data[:8]==b'\x89PNG\r\n\x1a\n'
    width,height=struct.unpack('>II',preview.data[16:24])
    assert width==height and width>=256
    assert preview.data==download.data==qr_png('https://family.scyllatech.cn/join/test-invite-a')
    assert download.headers['Content-Disposition'].startswith('attachment;')
    assert 'family-invite.png' in download.headers['Content-Disposition']
    assert 'no-store' in preview.headers['Cache-Control']
    inv=get_session().query(Invite).filter_by(id='qr-a').one()
    assert inv.used_count==0
    assert get_session().query(FamilyMember).count()==members_before


def test_qr_and_link_follow_configured_public_origin(client,login,app):
    add_invite()
    app.config['PUBLIC_BASE_URL']='https://new-family.example'
    login()
    png=client.get('/f/a/invites/qr-a/qr.png',headers={'X-Forwarded-Host':'attacker.example'})
    assert png.data==qr_png('https://new-family.example/join/test-invite-a')
    assert 'https://new-family.example/join/test-invite-a' in client.get('/f/a/manage').get_data(as_text=True)


def test_qr_requires_current_family_admin_permission(client,login):
    add_invite()
    add_invite(id='qr-b',family_id='b',code='test-invite-b')
    assert client.get('/f/a/invites/qr-a/qr.png').status_code==302
    login('member-a')
    assert client.get('/f/a/invites/qr-a/qr.png').status_code==403
    login()
    assert client.get('/f/a/invites/qr-b/qr.png').status_code==404
    assert client.get('/f/b/invites/qr-b/qr.png').status_code==404
    member=get_session().query(FamilyMember).filter_by(id='ma').one()
    member.del_flag=1;get_session().commit()
    assert client.get('/f/a/invites/qr-a/qr.png').status_code==404


@pytest.mark.parametrize('state',[
    {'expire_at':datetime.datetime.now()-datetime.timedelta(seconds=1)},
    {'used_count':2},
    {'del_flag':1},
])
def test_expired_used_or_deleted_invites_have_no_download(client,login,state):
    add_invite(**state)
    login()
    response=client.get('/f/a/invites/qr-a/qr.png')
    assert response.status_code==(404 if state.get('del_flag') else 410)
    assert '下载二维码（PNG）' not in client.get('/f/a/manage').get_data(as_text=True)


@pytest.mark.parametrize('value',['','ftp://example.com','https://example.com/path','https://example.com?x=1','https://user:password@example.com','https://example.com/#hash','https://example.com:bad','https://exam ple.com'])
def test_invalid_public_origin_is_rejected(value):
    with pytest.raises(ValueError):public_base_url(value)


def test_public_origin_normalizes_trailing_slash():
    assert public_base_url('https://family.scyllatech.cn/')=='https://family.scyllatech.cn'
