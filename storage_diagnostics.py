"""Safe OSS exception fields; never log messages, request URLs or headers."""
import re


def storage_error_details(error):
    try:
        from alibabacloud_oss_v2 import exceptions as oss_errors
    except ImportError:
        return {}
    if not isinstance(error,oss_errors.BaseError):
        return {}
    result={};chain=[];seen=set();current=error
    for _ in range(10):
        if current is None or id(current) in seen:break
        seen.add(id(current));chain.append(type(current).__name__)
        if isinstance(current,oss_errors.ServiceError):
            status=current.status_code
            if type(status) is int and 100<=status<=599:result['oss_status_code']=status
            for attr,pattern in [('code',r'[A-Za-z][A-Za-z0-9]{0,63}'),('ec',r'[0-9]{1,8}-[0-9]{1,16}'),('request_id',r'[A-Za-z0-9-]{1,128}')]:
                value=getattr(current,attr,None)
                if isinstance(value,str) and re.fullmatch(pattern,value):result['oss_'+attr]=value
            break
        if isinstance(current,(oss_errors.OperationError,oss_errors.RequestError,oss_errors.ResponseError)):
            inner=current.unwrap()
        else:inner=None
        current=inner if isinstance(inner,BaseException) else current.__cause__ or current.__context__
    result['storage_error_chain']=chain
    return result
