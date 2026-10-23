"""Allowlisted DB diagnostics: never stringify SQL, parameters or driver messages."""
import sqlite3

from pymysql.constants import ER
from pymysql.err import Error as MySQLError
from sqlalchemy.exc import DBAPIError


def database_details(error):
    if not isinstance(error, DBAPIError):
        return {}
    original = error.orig
    if isinstance(original, MySQLError):
        result = {'database_backend':'mysql'}
        args = original.args
        code = args[0] if args and type(args[0]) is int else None
        if code is not None and 0 <= code <= 65535:
            result['database_error_code'] = code
            if code in (ER.NO_SUCH_TABLE, ER.BAD_FIELD_ERROR):
                result['database_issue'] = 'schema_mismatch'
            elif code in (ER.DBACCESS_DENIED_ERROR, ER.ACCESS_DENIED_ERROR, ER.TABLEACCESS_DENIED_ERROR):
                result['database_issue'] = 'access_denied'
            elif code == ER.BAD_DB_ERROR:
                result['database_issue'] = 'unknown_database'
            elif code == ER.PARSE_ERROR:
                result['database_issue'] = 'sql_syntax'
        return result
    if isinstance(original, sqlite3.Error):
        result = {'database_backend':'sqlite'}
        code = getattr(original, 'sqlite_errorcode', None)
        if type(code) is int:
            result['database_error_code'] = code
        return result
    return {}
