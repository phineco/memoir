import pytest

from models import Person, get_session
from person_dates import tree_date_lines
from tests.test_spouse_tree import nodes
from views import _build_tree


@pytest.mark.parametrize('fields,expected', [
    ({'birth_solar_year':1950,'birth_solar_month':3,'birth_solar_day':8}, ['1950年3月8日[阳历]']),
    ({'birth_solar_year':1950}, ['1950年[阳历]']),
    ({'birth_solar_year':1950,'birth_solar_month':3}, ['1950年3月[阳历]']),
    ({'birth_lunar_year':1950,'birth_lunar_month':3,'birth_lunar_day':8,'birth_lunar_leap':True}, ['1950年闰3月8日[农历]']),
    ({'birth_lunar_month':3,'birth_lunar_day':8}, ['3月8日（年份不详）[农历]']),
    ({'birth_year':1942,'birth_calendar':'lunar'}, ['1942年[农历]']),
    ({'birth_solar_year':1950,'birth_lunar_year':1949}, ['1950年[阳历]','1949年[农历]']),
    ({}, []),
])
def test_tree_birth_precision_and_calendar(fields, expected):
    assert tree_date_lines(Person(**fields), 'birth') == expected


def test_tree_name_contains_relationship_and_preserves_other_information(app):
    s = get_session()
    parent = s.get(Person, 'pa')
    parent.name = '王桂兰'
    parent.gender = 'F'
    parent.relation = '长辈'
    parent.aliases = ['桂兰']
    parent.birth_solar_year = 1950
    parent.birth_solar_month = 3
    parent.birth_solar_day = 8
    parent.death_solar_year = 2020
    parent.death_solar_month = 6
    parent.death_solar_day = 1
    s.add(Person(id='child',family_id='a',name='孩子',parent_id='pa'))
    s.commit()
    with app.test_request_context():
        label = nodes(_build_tree('a', 'child'))['pa']['name']
        fallback = nodes(_build_tree('a'))['pa']['name']
    assert label.splitlines()[0] == '王桂兰[母亲]'
    assert fallback.splitlines()[0] == '王桂兰[长辈]'
    assert '对你：' not in label
    assert '1950年3月8日[阳历]' in label
    assert '去世：2020年6月1日[阳历]' in label
    assert '别名：桂兰' in label
