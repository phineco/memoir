#!/usr/bin/env python3
"""Run the persistent organizer queue; no real calls unless explicitly configured."""
import argparse
from pathlib import Path
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app import create_app
from models import remove_session
from organize_jobs import run_one


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--once', action='store_true')
    parser.add_argument('--queue', choices=('all','organize','question','asr'), default='all')
    args = parser.parse_args()
    app = create_app()
    while True:
        with app.app_context():
            try:
                from interview_questions import run_one as question_one
                from interview_asr import run_one as asr_one
                queues={'organize':run_one,'question':question_one,'asr':asr_one}
                worked=False
                for name,process in queues.items():
                    if args.queue in ('all',name):worked=process() or worked
                if args.queue in ('all','asr'):
                    from interview_materials import purge_one
                    worked=purge_one() or worked
            finally:
                remove_session()
        if args.once:
            return 0
        if not worked:
            time.sleep(2)


if __name__ == '__main__':
    raise SystemExit(main())
