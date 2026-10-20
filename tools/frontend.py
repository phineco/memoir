#!/usr/bin/env python3
"""Pinned standalone Tailwind build; the production host needs Python only."""
import argparse
import gzip
import hashlib
import io
import json
import os
from pathlib import Path
import platform
import re
import subprocess
import tarfile
import tempfile
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
LOCK = json.loads((ROOT / 'tools/frontend.lock.json').read_text())
DIST = ROOT / 'static/dist'


def sha(data):
    return hashlib.sha256(data).hexdigest()


def binary_name():
    system = {'Darwin':'macos','Linux':'linux','Windows':'windows'}.get(platform.system())
    arch = {'arm64':'arm64','aarch64':'arm64','x86_64':'x64','AMD64':'x64'}.get(platform.machine())
    name = f'tailwindcss-{system}-{arch}' + ('.exe' if system == 'windows' else '')
    if name not in LOCK['tailwind']['binaries']:
        raise SystemExit('Unsupported build platform; use the Linux CI build.')
    return name


def compiler(bootstrap=False):
    name = binary_name()
    path = Path(os.environ.get('TAILWIND_BIN', ROOT / '.tools' / name)).resolve()
    if not path.exists() and bootstrap:
        path.parent.mkdir(parents=True, exist_ok=True)
        with urllib.request.urlopen(LOCK['tailwind']['base_url'] + name, timeout=60) as response:
            data = response.read()
        if sha(data) != LOCK['tailwind']['binaries'][name]:
            raise SystemExit('Tailwind download checksum mismatch')
        path.write_bytes(data)
        path.chmod(0o755)
    if not path.is_file():
        raise SystemExit('Run python tools/frontend.py bootstrap, or set TAILWIND_BIN to the pinned binary.')
    if sha(path.read_bytes()) != LOCK['tailwind']['binaries'][name]:
        raise SystemExit('Tailwind checksum mismatch; refusing to execute')
    return path


def verify_vendor():
    for filename, entry in LOCK['vendor'].items():
        if sha((ROOT / filename).read_bytes()) != entry['sha256']:
            raise SystemExit(f'Vendor checksum mismatch: {filename}')


def outputs():
    verify_vendor()
    with tempfile.TemporaryDirectory(prefix='memoir-css-') as temp:
        target = Path(temp) / 'tailwind.css'
        subprocess.run([str(compiler()), '-c', 'tailwind.config.js', '-i', 'static/src.css', '-o', str(target), '--minify'], cwd=ROOT, check=True)
        css = target.read_bytes() + b'\n' + (ROOT / 'static/ui.css').read_bytes()
    sources = {'app.css':css}
    for name in ['preferences.js','read-aloud.js','family-context.js']:
        sources[name] = (ROOT / 'static' / name).read_bytes()
    for path in LOCK['vendor']:
        if path.endswith(('.css','.js')):
            sources[path.removeprefix('static/')] = (ROOT / path).read_bytes()
    files, hashes, data = {}, {}, {}
    for logical, content in sorted(sources.items()):
        source = Path(logical)
        filename = f'{source.stem}.{sha(content)[:16]}{source.suffix}'
        files[logical] = filename
        hashes[filename] = sha(content)
        data[filename] = content
    manifest = {'version':1,'files':files,'sha256':hashes}
    data['manifest.json'] = (json.dumps(manifest,indent=2,sort_keys=True) + '\n').encode()
    return data


def build(check=False):
    data = outputs()
    if check:
        actual = {p.name:p.read_bytes() for p in DIST.glob('*') if p.is_file()}
        if actual != data:
            raise SystemExit('Static bundle is stale. Run python tools/frontend.py build and commit static/dist/.')
    else:
        DIST.mkdir(exist_ok=True)
        for path in DIST.iterdir():
            if path.is_file():
                path.unlink()
        for filename, content in data.items():
            (DIST / filename).write_bytes(content)
    print(f'{"Verified" if check else "Built"} {len(data)-1} fingerprinted assets')


def verify_bundle():
    verify_vendor()
    manifest = json.loads((DIST / 'manifest.json').read_text())
    for name, digest in manifest['sha256'].items():
        if Path(name).name != name or sha((DIST / name).read_bytes()) != digest:
            raise SystemExit(f'Invalid bundle asset: {name}')
    return manifest


def release(version, output):
    if not version or not re.fullmatch(r'[a-zA-Z0-9][a-zA-Z0-9._-]{0,63}', version):
        raise SystemExit('Supply --version with a safe release name')
    verify_bundle()
    allowed_dirs = ['templates','static','migrations','tools','tests']
    files = [p for p in ROOT.iterdir() if p.is_file() and (p.suffix in {'.py','.md','.sql'} or p.name.startswith('requirements') and p.suffix == '.txt' or p.name in {'.env.example','install.sh','tailwind.config.js','package.json','package-lock.json'})]
    for name in allowed_dirs:
        files += [p for p in (ROOT / name).rglob('*') if p.is_file() and '__pycache__' not in p.parts and p.suffix != '.pyc']
    contents = {}
    for path in sorted(set(files)):
        if path.is_symlink():
            raise SystemExit(f'Refusing symlink in release: {path}')
        contents[path.relative_to(ROOT).as_posix()] = path.read_bytes()
    revision = subprocess.run(['git','rev-parse','HEAD'],cwd=ROOT,capture_output=True,text=True)
    info = {'version':version,'revision':revision.stdout.strip() if revision.returncode == 0 else 'working-tree', 'sha256':{n:sha(b) for n,b in contents.items()}}
    contents['RELEASE.json'] = (json.dumps(info,indent=2,sort_keys=True)+'\n').encode()
    output = Path(output).resolve()
    if output.exists():
        raise SystemExit(f'Release already exists: {output}')
    output.parent.mkdir(parents=True,exist_ok=True)
    with output.open('xb') as raw, gzip.GzipFile(filename='',mode='wb',fileobj=raw,mtime=0) as zipped, tarfile.open(fileobj=zipped,mode='w') as archive:
        for name, content in sorted(contents.items()):
            item = tarfile.TarInfo(f'memoir-{version}/{name}')
            item.size=len(content); item.mode=0o644; item.mtime=0
            archive.addfile(item,io.BytesIO(content))
    print(f'Release: {output}\nSHA256: {sha(output.read_bytes())}')


def verify_release():
    info = json.loads((ROOT / 'RELEASE.json').read_text())
    for name, digest in info['sha256'].items():
        path = ROOT / name
        if path.is_symlink() or ROOT not in path.resolve().parents or sha(path.read_bytes()) != digest:
            raise SystemExit(f'Release checksum mismatch: {name}')
    print('Release files verified')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command',choices=['bootstrap','build','check','verify','verify-release','release'])
    parser.add_argument('--version')
    parser.add_argument('--output')
    args = parser.parse_args()
    if args.command == 'bootstrap': print(compiler(bootstrap=True))
    elif args.command in {'build','check'}: build(check=args.command == 'check')
    elif args.command == 'verify': verify_bundle(); print('Vendor and bundle hashes verified')
    elif args.command == 'verify-release': verify_release()
    else:
        if not args.output: parser.error('--output is required for release')
        release(args.version,args.output)


if __name__ == '__main__':
    main()
