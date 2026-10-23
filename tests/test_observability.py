import json
import logging

from observability import release_version


def test_version_can_be_read_without_git_and_rejects_untrusted_text(tmp_path):
    (tmp_path/'RELEASE.json').write_text(json.dumps({'revision':'abc123def456'}))
    assert release_version(tmp_path)=='abc123def456'
    assert release_version(tmp_path,'<bad>')=='unknown'


def test_request_id_and_timing_do_not_log_sensitive_query_or_body(app,client,caplog):
    app.config['REQUEST_LOGGING']=True
    with caplog.at_level(logging.INFO):
        response=client.get('/login?password=SENSITIVE_QUERY',headers={'X-Request-ID':'untrusted-secret'})
    assert len(response.headers['X-Request-ID'])==24
    assert response.headers['X-Request-ID']!='untrusted-secret'
    assert 'db;dur=' in response.headers['Server-Timing']
    assert 'SENSITIVE_QUERY' not in caplog.text and 'untrusted-secret' not in caplog.text


def test_fault_page_and_json_share_safe_diagnostics(app,client,caplog):
    @app.route('/synthetic-fault',methods=['GET','POST'])
    def fail():raise RuntimeError('PRIVATE_BODY_SECRET')
    with caplog.at_level(logging.ERROR):
        response=client.get('/synthetic-fault')
        identifier=response.headers['X-Request-ID']
        assert response.status_code==500 and identifier in response.get_data(as_text=True)
        assert identifier in caplog.text and 'RuntimeError' in caplog.text
        assert 'PRIVATE_BODY_SECRET' not in caplog.text
        response=client.post('/synthetic-fault',json={'question':'PRIVATE_QUESTION'})
    assert response.status_code==500 and response.json['request_id']==response.headers['X-Request-ID']
    assert 'PRIVATE_QUESTION' not in caplog.text and 'PRIVATE_BODY_SECRET' not in response.get_data(as_text=True)


def test_handled_http_errors_have_visible_reference_and_failed_sql_does_not_log_parameters(app,client,caplog):
    from sqlalchemy import text
    from models import get_session
    @app.route('/sql-fault')
    def sql_fault():get_session().execute(text("SELECT 'PRIVATE_SQL_LITERAL' FROM nonexistent_table"))
    response=client.get('/missing-page?secret=PRIVATE_QUERY')
    assert response.status_code==404 and response.headers['X-Request-ID'] in response.get_data(as_text=True)
    assert response.headers['X-Request-ID'] in caplog.text and 'PRIVATE_QUERY' not in caplog.text
    response=client.get('/sql-fault')
    assert response.status_code==500 and '1 queries' in response.headers['Server-Timing']
    assert 'PRIVATE_SQL_LITERAL' not in caplog.text and 'PRIVATE_SQL_LITERAL' not in response.get_data(as_text=True)
