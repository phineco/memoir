import importlib.util
import json
from pathlib import Path
import shutil
import tarfile

ROOT = Path(__file__).resolve().parents[1]


def test_fingerprinted_assets_and_html_cache_policy(client):
    manifest = json.loads((ROOT / 'static/dist/manifest.json').read_text())
    asset = manifest['files']['app.css']
    response = client.get('/static/dist/' + asset)
    assert response.status_code == 200
    assert 'immutable' in response.headers['Cache-Control']
    cached=client.get('/static/dist/'+asset,headers={'If-None-Match':response.headers['ETag']})
    assert cached.status_code == 304
    assert 'immutable' in cached.headers['Cache-Control']
    assert client.get('/').headers['Cache-Control'] == 'no-store'
    assert 'immutable' not in client.get('/static/dist/manifest.json').headers['Cache-Control']


def test_release_is_repeatable_and_excludes_live_data(tmp_path, monkeypatch):
    spec = importlib.util.spec_from_file_location('frontend', ROOT / 'tools/frontend.py')
    frontend = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(frontend)
    source = tmp_path / 'project'
    source.mkdir()
    for directory in ['static','templates','migrations','tools']:
        shutil.copytree(ROOT / directory, source / directory)
    (source / '.env').write_text('must-not-ship-secret')
    (source / 'memoir.db').write_text('must-not-ship-database')
    (source / '.env.example').write_text('SECRET_KEY=replace-me')
    (source / 'uploads').mkdir()
    (source / 'uploads/private.jpg').write_text('must-not-ship-photo')
    monkeypatch.setattr(frontend,'ROOT',source)
    monkeypatch.setattr(frontend,'DIST',source / 'static/dist')
    first, second = tmp_path/'one.tar.gz', tmp_path/'two.tar.gz'
    frontend.release('test',first)
    frontend.release('test',second)
    assert first.read_bytes() == second.read_bytes()
    with tarfile.open(first) as archive:
        names = archive.getnames()
        assert all('/uploads/' not in n and not n.endswith('/.env') and not n.endswith('.db') for n in names)
        assert 'memoir-test/.env.example' in names
        info=json.load(archive.extractfile('memoir-test/RELEASE.json'))
        for filename, digest in info['sha256'].items():
            assert frontend.sha(archive.extractfile('memoir-test/'+filename).read()) == digest
