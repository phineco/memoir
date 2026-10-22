"""Independent partial solar/lunar life dates; never infer a conversion."""
import calendar

EVENTS = {'birth': '出生', 'death': '去世'}
CALENDARS = {'solar': '公历', 'lunar': '农历'}
PARTS = ('year', 'month', 'day')
DATE_FIELDS = tuple(
    f'{event}_{kind}_{part}'
    for event in EVENTS for kind in CALENDARS for part in PARTS
) + tuple(f'{event}_lunar_leap' for event in EVENTS)
LUNAR_MONTHS = ('正月', '二月', '三月', '四月', '五月', '六月',
                '七月', '八月', '九月', '十月', '十一月', '十二月')
LUNAR_DAYS = tuple(
    ['初' + n for n in '一二三四五六七八九'] + ['初十']
    + ['十' + n for n in '一二三四五六七八九'] + ['二十']
    + ['廿' + n for n in '一二三四五六七八九'] + ['三十']
)


def values(person, event, kind):
    result = {part: getattr(person, f'{event}_{kind}_{part}', None) for part in PARTS}
    # Older seed/import records can still have only the legacy year attributes.
    legacy_calendar = getattr(person, event + '_calendar', None) or 'solar'
    if not any(result.values()) and legacy_calendar == kind:
        result['year'] = getattr(person, event + '_year', None)
    return result


def form_values(person):
    result = {}
    for event in EVENTS:
        for kind in CALENDARS:
            result.update({
                f'{event}_{kind}_{part}': value if value is not None else ''
                for part, value in values(person, event, kind).items()
            })
        result[event + '_lunar_leap'] = bool(getattr(person, event + '_lunar_leap', False))
    return result


def _number(raw, maximum, label):
    if raw is None or str(raw).strip() == '':
        return None
    if isinstance(raw, bool):
        raise ValueError(label + '请填整数')
    try:
        value = int(str(raw).strip())
    except (TypeError, ValueError):
        raise ValueError(label + '请填整数') from None
    if not 1 <= value <= maximum:
        raise ValueError(f'{label}须在 1–{maximum} 之间')
    return value


def _validate(parts, kind, leap, label):
    year, month, day = (parts[part] for part in PARTS)
    if day and not month:
        raise ValueError(label + '填写日时也需要填写月份')
    if leap and not month:
        raise ValueError(label + '标记闰月时需要填写月份')
    # Unknown years may include February 29; do not infer the year.
    if kind == 'solar' and month and day:
        if day > calendar.monthrange(year or 2000, month)[1]:
            raise ValueError(label + '不是有效的公历日期')


def legacy_fields(result):
    for event in EVENTS:
        solar = result[event + '_solar_year']
        lunar = result[event + '_lunar_year']
        result[event + '_year'] = solar or lunar
        result[event + '_calendar'] = 'solar' if solar or not lunar else 'lunar'
    return result


def _check_chronology(result, kind):
    birth = [result[f'birth_{kind}_{part}'] for part in PARTS]
    death = [result[f'death_{kind}_{part}'] for part in PARTS]
    if kind == 'lunar':
        birth.insert(2, int(result['birth_lunar_leap']))
        death.insert(2, int(result['death_lunar_leap']))
    for born, died in zip(birth, death):
        # Compare only the prefix known for both dates, within one calendar.
        if born is None or died is None or died > born:
            break
        if died < born:
            raise ValueError('同一历法的去世日期不能早于出生日期')


def parse_form(form, person=None):
    prior = form_values(person) if person is not None else {}
    result = {}
    for event, title in EVENTS.items():
        for kind, calendar_title in CALENDARS.items():
            prefix = f'{event}_{kind}'
            parts = {}
            for part, maximum, part_title in (
                ('year', 9999, '年'), ('month', 12, '月'),
                ('day', 31 if kind == 'solar' else 30, '日'),
            ):
                field = f'{prefix}_{part}'
                parts[part] = _number(form.get(field, prior.get(field)), maximum,
                                      title + calendar_title + part_title)
                result[field] = parts[part]
            if kind == 'lunar':
                leap_field = event + '_lunar_leap'
                posted = any(f'{prefix}_{part}' in form for part in PARTS) or leap_field in form
                result[leap_field] = (
                    form.get(leap_field) in ('1', 'on', 'true', True)
                    if posted else bool(prior.get(leap_field))
                )
        # Older clients can still send a single year plus its calendar.
        event_fields = [field for field in DATE_FIELDS if field.startswith(event + '_')]
        if not any(field in form for field in event_fields) and event + '_year' in form:
            kind = 'lunar' if form.get(event + '_calendar') == 'lunar' else 'solar'
            result[f'{event}_{kind}_year'] = _number(form.get(event + '_year'), 9999, title + '年')
    for event, title in EVENTS.items():
        for kind, calendar_title in CALENDARS.items():
            parts = {part: result[f'{event}_{kind}_{part}'] for part in PARTS}
            leap = result[event + '_lunar_leap'] if kind == 'lunar' else False
            _validate(parts, kind, leap, title + calendar_title)
    if (form.get('life_status') == 'alive' or form.get('alive') in ('1', 'on', 'true', True)) and any(result[field] for field in DATE_FIELDS if field.startswith('death_')):
        raise ValueError('健在与去世日期不能同时填写，请核对后再保存')
    for kind in CALENDARS:
        _check_chronology(result, kind)
    return legacy_fields(result)


def date_label(person, event):
    labels = []
    for kind, title in CALENDARS.items():
        parts = values(person, event, kind)
        if not any(parts.values()):
            continue
        year, month, day = (parts[part] for part in PARTS)
        label = title + ' ' + (str(year) + '年' if year else '')
        if month:
            if kind == 'lunar':
                label += ('闰' if getattr(person, event + '_lunar_leap', False) else '')
                label += LUNAR_MONTHS[month - 1]
            else:
                label += str(month) + '月'
        if day:
            label += LUNAR_DAYS[day - 1] if kind == 'lunar' else str(day) + '日'
        if not year:
            label += '（年份不详）'
        labels.append(label)
    return ' / '.join(labels)


def sync_legacy_year(person, event, raw):
    """Year-only imports cannot silently contradict family-entered dates."""
    year = _number(raw, 9999, event + 'Year')
    if year is None:
        return
    kind = 'lunar' if getattr(person, event + '_calendar', None) == 'lunar' else 'solar'
    current = values(person, event, kind)
    other = values(person, event, 'solar' if kind == 'lunar' else 'lunar')
    if current['year'] != year and (current['month'] or current['day'] or any(other.values())):
        raise ValueError('年份与已有双历日期冲突，请在人物编辑页核实修改')
    setattr(person, f'{event}_{kind}_year', year)
    setattr(person, event + '_year', year)
    setattr(person, event + '_calendar', kind)


def parse_life_state(form, dates, person=None):
    state = form.get('life_status')
    has_death = any(dates.get(field) for field in DATE_FIELDS if field.startswith('death_'))
    if state is None:
        if form.get('alive') in ('1', 'on', 'true', True):
            state = 'alive'
        elif has_death:
            state = 'deceased'
        else:
            state = 'unknown'
    if state not in ('unknown', 'alive', 'deceased'):
        raise ValueError('请选择有效的生存状态')
    if state == 'alive' and has_death:
        raise ValueError('健在与去世日期不能同时填写')
    if state == 'unknown' and has_death:
        state = 'deceased'
    return state
