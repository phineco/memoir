"""ISO 周年与周数统一口径；旧链接缺省到当前 ISO 年。"""
import datetime
from zoneinfo import ZoneInfo

from config import Config


def local_now():
    """New publication/revision timestamps use the same local clock as weekly boundaries."""
    return datetime.datetime.now(ZoneInfo(Config.APP_TIMEZONE)).replace(tzinfo=None)


def current_period():
    today = local_now().date()
    year, week, _ = today.isocalendar()
    return year, week


def report_period(week=None, year=None):
    current_year, current_week = current_period()
    year = current_year if year is None else int(year)
    week = current_week if week is None else int(week)
    start = datetime.date.fromisocalendar(year, week, 1)
    end = start + datetime.timedelta(days=7)
    return year, week, datetime.datetime.combine(start, datetime.time()), \
        datetime.datetime.combine(end, datetime.time())


def weekly_cache_key(family_id, year, week):
    year, week, _, _ = report_period(week, year)
    return f"weekly:{family_id}:{year}:{week}"
