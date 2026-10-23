#!/usr/bin/env python3
"""Repeatable isolated application/SQL measurements; never a production load test."""
import argparse
import datetime
import json
import math
import os
from pathlib import Path
import re
import sys
import tempfile
import time


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--size',type=int,default=1000)
    parser.add_argument('--samples',type=int,default=20)
    parser.add_argument('--output',required=True)
    args=parser.parse_args()
    if not 0<=args.size<=10000 or not 2<=args.samples<=200:parser.error('size 0..10000; samples 2..200')
    sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
    with tempfile.TemporaryDirectory(prefix='memoir-baseline-') as directory:
        os.environ.update(DATABASE_URL='sqlite:///'+str(Path(directory)/'test.db'),STORAGE_BACKEND='local',
                          UPLOAD_DIR=str(Path(directory)/'uploads'),DEEPSEEK_API_KEY='',APP_ENV='local',
                          ALIYUN_SMS_ACCESS_KEY_ID='',SMS_DEVELOPMENT_MODE='0')
        from app import app
        import models
        models.Base.metadata.create_all(models._engine)
        app.config.update(TESTING=True,SECRET_KEY='isolated-baseline-only')
        s=models.get_session()
        now=datetime.datetime.now()
        s.add_all([models.User(id='benchmark-user',nickname='Synthetic'),
                   models.Family(id='benchmark',name='Synthetic',owner_user_id='benchmark-user'),
                   models.FamilyMember(id='benchmark-member',family_id='benchmark',user_id='benchmark-user',role='owner')])
        for index in range(args.size):
            identifier='story-%06d'%index
            s.add(models.Interview(id=identifier,family_id='benchmark',author_id='benchmark-user',topic='Synthetic story',publish_status='published',visibility='public',published_at=now))
            s.add(models.Draft(id='draft-'+identifier,interview_id=identifier,version=1,is_current=True,content='Synthetic paragraph. '*80))
        s.commit()
        client=app.test_client()
        with client.session_transaction() as session:session['user_id']='benchmark-user'
        from reporting import current_period
        year,week=current_period()
        paths=['/f/benchmark','/f/benchmark/stories','/f/benchmark/weekly/%s/%s'%(year,week),'/f/benchmark/ask']
        if args.size:paths.insert(2,'/f/benchmark/story/story-000000')
        rows=[]
        for path in paths:
            measurements=[]
            for iteration in range(args.samples+1):
                started=time.perf_counter();response=client.get(path)
                if response.status_code!=200:raise RuntimeError('Isolated page failed: '+path)
                timing=response.headers['Server-Timing']
                measurement=dict(round_trip_ms=round((time.perf_counter()-started)*1000,2),
                    app_ms=float(re.search(r'app;dur=([\d.]+)',timing).group(1)),
                    sql_ms=float(re.search(r'db;dur=([\d.]+)',timing).group(1)),
                    queries=int(re.search(r'(\d+) queries',timing).group(1)),bytes=len(response.data))
                if iteration==0:cold=measurement
                else:measurements.append(measurement)
            rows.append(dict(path=path,cold=cold,samples=args.samples,p95={
                key:sorted(row[key] for row in measurements)[math.ceil(.95*len(measurements))-1] for key in measurements[0]}))
        result=dict(version=app.config['RELEASE_VERSION'],dataset=args.size,engine='isolated SQLite',
                    scope='Flask test client; no network, browser rendering, external AI or static asset transfer',pages=rows)
        Path(args.output).write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
        print('Isolated baseline written; %d stories, %d warm samples per page.'%(args.size,args.samples))
        models.remove_session();models._engine.dispose()


if __name__=='__main__':main()
