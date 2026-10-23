#!/usr/bin/env python3
"""Run bounded voice jobs using the deployed configuration. No fake provider in this command."""
import argparse
from pathlib import Path
import sys
import signal
import threading

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--limit',type=int,default=10)
    parser.add_argument('--watch',action='store_true',help='Poll every two seconds; stop gracefully after the current step')
    args=parser.parse_args()
    if not 1<=args.limit<=100:parser.error('limit must be 1..100')
    from app import app
    from voice_worker import process_one
    from models import remove_session
    stopped=threading.Event();count=0
    if args.watch:
        signal.signal(signal.SIGTERM,lambda *args:stopped.set())
        signal.signal(signal.SIGINT,lambda *args:stopped.set())
    with app.app_context():
        while not stopped.is_set():
            worked=process_one();remove_session()
            if worked:count+=1
            if not args.watch and (not worked or count>=args.limit):break
            if args.watch and not worked:stopped.wait(2)
    print('Voice queue steps: %d. Inspect lifecycle states for success; step count is not a provider receipt.'%count)


if __name__=='__main__':main()
