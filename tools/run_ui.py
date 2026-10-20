#!/usr/bin/env python3
"""Start a disposable local app, run browser checks, and always stop it."""
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request

root = Path(__file__).resolve().parents[1]
with socket.socket() as sock:
    sock.bind(('127.0.0.1',0))
    port = sock.getsockname()[1]
env = dict(os.environ, UI_TEST_PORT=str(port), UI_TEST_URL=f'http://127.0.0.1:{port}', PYTHONDONTWRITEBYTECODE='1')
with tempfile.TemporaryFile(mode='w+') as log:
    server = subprocess.Popen([sys.executable,'-B','tests/ui_server.py'], cwd=root,env=env,stdout=log,stderr=log)
    try:
        for _ in range(120):
            if server.poll() is not None:
                log.seek(0); raise RuntimeError(log.read())
            try:
                with urllib.request.urlopen(env['UI_TEST_URL']+'/login',timeout=1): break
            except OSError: time.sleep(.25)
        else: raise RuntimeError('Local UI server did not become ready')
        result = subprocess.run(['node','tests/ui-checks.cjs'],cwd=root,env=env)
        if result.returncode:
            log.seek(0); print(log.read(),file=sys.stderr)
        sys.exit(result.returncode)
    finally:
        server.terminate()
        try: server.wait(timeout=5)
        except subprocess.TimeoutExpired: server.kill();server.wait()
