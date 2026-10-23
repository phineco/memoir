#!/usr/bin/env python3
"""Preview or remove browser status samples older than 90 days; never touches stories."""
import argparse
import datetime as dt
from pathlib import Path
import sys

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))


def expire_samples(session,now,apply=False):
    from models import UsageEvent
    cutoff=now-dt.timedelta(days=90)
    query=session.query(UsageEvent).filter(UsageEvent.create_date<cutoff)
    count=query.count()
    if apply:
        query.delete(synchronize_session=False)
        session.commit()
    return count


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--apply',action='store_true',help='Delete expired status samples (default: preview only)')
    args=parser.parse_args()
    from config import Config
    from models import get_session,init_db,remove_session
    from reporting import local_now
    init_db(Config.DATABASE_URL,pool_recycle_seconds=Config.DB_POOL_RECYCLE_SECONDS)
    try:
        count=expire_samples(get_session(),local_now(),args.apply)
        print('%s: %d browser status samples older than 90 days.'%('Removed' if args.apply else 'Preview',count))
    finally:remove_session()


if __name__=='__main__':main()
