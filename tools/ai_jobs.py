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
    args = parser.parse_args()
    app = create_app()
    while True:
        with app.app_context():
            try:
                from interview_questions import run_one as question_one
                worked = run_one()
                worked = question_one() or worked
            finally:
                remove_session()
        if args.once:
            return 0
        if not worked:
            time.sleep(2)


if __name__ == '__main__':
    raise SystemExit(main())
