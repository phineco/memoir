"""Safe request diagnostics: no bodies, SQL parameters, query strings or secrets."""
import json
import logging
from pathlib import Path
import re
import secrets
import subprocess
import time
import traceback

from flask import current_app, g, has_request_context, jsonify, render_template, request
from sqlalchemy import event
from werkzeug.exceptions import HTTPException


def release_version(root, configured=''):
    candidate=configured
    if not candidate:
        try:
            data=json.loads((Path(root)/'RELEASE.json').read_text())
            candidate=data.get('revision') or data.get('version')
        except (OSError,ValueError,AttributeError):
            try:
                candidate=subprocess.run(['git','-C',str(root),'rev-parse','--short=12','HEAD'],
                                         capture_output=True,text=True,timeout=1,check=True).stdout.strip()
            except (OSError,subprocess.SubprocessError):candidate='development'
    return candidate if isinstance(candidate,str) and re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._-]{0,63}',candidate) else 'unknown'


def record_error(error, kind='request'):
    if not has_request_context():return
    frames=traceback.extract_tb(error.__traceback__) if error.__traceback__ else []
    current_app.logger.error(json.dumps(dict(
        event='failure',kind=kind,request_id=g.get('request_id'),version=current_app.config['RELEASE_VERSION'],
        endpoint=request.endpoint,method=request.method,error_type=type(error).__name__,
        stack=[dict(file=Path(frame.filename).name,line=frame.lineno,function=frame.name) for frame in frames]),ensure_ascii=False))


def install(app, engine):
    app.config['RELEASE_VERSION']=release_version(app.root_path,app.config.get('APP_VERSION',''))
    if app.config.get('REQUEST_LOGGING'):app.logger.setLevel(logging.INFO)

    @event.listens_for(engine,'before_cursor_execute')
    def before_sql(conn,cursor,statement,parameters,context,executemany):
        if has_request_context():context._memoir_started=time.perf_counter()

    @event.listens_for(engine,'after_cursor_execute')
    def after_sql(conn,cursor,statement,parameters,context,executemany):
        if has_request_context() and hasattr(context,'_memoir_started'):
            g.sql_ms=g.get('sql_ms',0)+(time.perf_counter()-context._memoir_started)*1000
            g.sql_count=g.get('sql_count',0)+1

    @app.before_request
    def begin_request():
        g.request_id=secrets.token_hex(12)
        g.request_started=time.perf_counter()
        g.sql_count=0;g.sql_ms=0

    @app.after_request
    def finish_request(response):
        identifier=g.get('request_id','')
        response.headers['X-Request-ID']=identifier
        response.headers['X-App-Version']=app.config['RELEASE_VERSION']
        duration=(time.perf_counter()-g.get('request_started',time.perf_counter()))*1000
        response.headers['Server-Timing']='app;dur=%.2f, db;dur=%.2f, sql;desc="%d queries"' % (duration,g.get('sql_ms',0),g.get('sql_count',0))
        if response.status_code>=400 and response.is_json:
            payload=response.get_json(silent=True)
            if isinstance(payload,dict):
                payload['request_id']=identifier;response.set_data(app.json.dumps(payload))
        if app.config.get('REQUEST_LOGGING') or response.status_code>=400:
            app.logger.log(logging.WARNING if response.status_code>=400 else logging.INFO,json.dumps(dict(event='request',request_id=identifier,version=app.config['RELEASE_VERSION'],
                endpoint=request.endpoint,method=request.method,status=response.status_code,
                app_ms=round(duration,2),sql_ms=round(g.get('sql_ms',0),2),sql_count=g.get('sql_count',0))))
        return response

    @app.errorhandler(Exception)
    def unexpected_error(error):
        if isinstance(error,HTTPException):return error
        record_error(error)
        # This template has no DB-dependent context processors or family data.
        if request.is_json or request.path.startswith('/api/'):
            return jsonify(error='暂时无法完成，请稍后重试',request_id=g.request_id),500
        return app.jinja_env.get_template('error.html').render(request_id=g.request_id),500
