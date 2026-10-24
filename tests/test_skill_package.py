"""Check the installable skill artifact, without invoking its workflow."""
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]
SKILL = ROOT / 'skill/memoir-organizer'


def test_skill_frontmatter_loads_with_standard_yaml_parser():
    text = (SKILL / 'SKILL.md').read_text()
    assert text.startswith('---\n')
    metadata = yaml.safe_load(text.split('---', 2)[1])
    assert metadata['name'] == SKILL.name
    assert isinstance(metadata['description'], str) and metadata['description'].strip()
    assert isinstance(metadata.get('metadata', {}), dict)
