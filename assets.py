"""Resolve immutable static files from the committed build manifest."""
import json
from pathlib import Path
from flask import url_for


def asset_resolver(root):
    manifest = json.loads((Path(root) / 'static/dist/manifest.json').read_text())
    files = manifest['files']

    def asset_url(name):
        return url_for('static', filename='dist/' + files[name])

    return asset_url
