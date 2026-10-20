"""阿里云短信：Dysmsapi SendSms（V3 签名 ACS3-HMAC-SHA256 直调，无需官方 SDK）。

参考：https://api.aliyun.com/document/Dysmsapi/2017-05-25/SendSms
签名：https://help.aliyun.com/zh/sdk/product-overview/v3-request-structure-and-signature

- send_code(phone, purpose): 生成 6 位验证码 → 入库 → 发短信。
  未配置 AK 时为开发模式：验证码写服务日志，API 直接返回 code（仅原型测试用）。
- verify_code(phone, code, purpose): 校验（10 分钟有效，一次性使用）。
"""
import datetime
import hashlib
import hmac
import logging
import random
import uuid
from urllib.parse import quote

import requests

from config import Config
from models import SmsCode, get_session, new_id

log = logging.getLogger(__name__)

CODE_TTL_MINUTES = 10
RESEND_COOLDOWN_SECONDS = 60
PURPOSES = ("register", "reset", "login")


class SMSError(Exception):
    pass


def sms_enabled():
    return bool(Config.SMS_ENABLED)


def _s():
    return get_session()


# ---------------- V3 签名（ACS3-HMAC-SHA256） ----------------
# 参考：https://help.aliyun.com/zh/sdk/product-overview/v3-request-structure-and-signature

def _pct(s):
    """RFC3986 编码：空格→%20，*→%2A，~ 不编码（大小写十六进制均可，统一大写）。"""
    return quote(str(s), safe="").replace("+", "%20") \
        .replace("*", "%2A").replace("%7E", "~")


def _sha256_hex(s):
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


def _v3_sign(method, host, query_params, body, ak, secret,
             action, version, date=None, nonce=None):
    """V3 签名，返回 (signed_headers_dict, authorization, query_string)。

    用官方工作示例验算：
    AK=YourAccessKeyId/Secret=YourAccessKeySecret, nonce=3156853299f313e23d1673dc12e1703d,
    date=2023-10-26T10:22:32Z, action=RunInstances, version=2014-05-26,
    host=ecs.cn-shanghai.aliyuncs.com, query={ImageId, RegionId}, POST 空 body
    → HashedCanonicalRequest=7ea06492da5221eba5297e897ce16e55f964061054b7695beedaac1145b1e259
    → Signature=06563a9e1b43f5dfe96b81484da74bceab24a1d853912eee15083a6f0f3283c0
    """
    date = date or datetime.datetime.now(datetime.timezone.utc) \
        .strftime("%Y-%m-%dT%H:%M:%SZ")
    nonce = nonce or uuid.uuid4().hex
    hashed_payload = _sha256_hex(body or "")
    headers = {
        "host": host,
        "x-acs-action": action,
        "x-acs-content-sha256": hashed_payload,
        "x-acs-date": date,
        "x-acs-signature-nonce": nonce,
        "x-acs-version": version,
    }
    canonical_qs = "&".join(
        "%s=%s" % (_pct(k), _pct(v)) for k, v in sorted(query_params.items()))
    canon_headers = "".join(
        "%s:%s\n" % (k, str(headers[k]).strip())
        for k in sorted(headers))
    signed_headers = ";".join(sorted(headers))
    canonical_request = "\n".join(
        [method, "/", canonical_qs, canon_headers.rstrip("\n"), "",
         signed_headers, hashed_payload])
    string_to_sign = "ACS3-HMAC-SHA256\n" + _sha256_hex(canonical_request)
    signature = hmac.new(secret.encode("utf-8"),
                         string_to_sign.encode("utf-8"),
                         hashlib.sha256).hexdigest()
    authorization = ("ACS3-HMAC-SHA256 Credential=%s,"
                     "SignedHeaders=%s,Signature=%s"
                     % (ak, signed_headers, signature))
    out_headers = {k: str(v) for k, v in headers.items()}
    out_headers["Authorization"] = authorization
    return out_headers, canonical_qs


def _send_sms_api(phone, template_param):
    """V3 签名直调 SendSms（POST，参数放 query，空 body）。成功返回 True。"""
    host = Config.ALIYUN_SMS_ENDPOINT
    query = {
        "PhoneNumbers": phone,
        "SignName": Config.ALIYUN_SMS_SIGN_NAME,
        "TemplateCode": Config.ALIYUN_SMS_TEMPLATE_CODE,
        "TemplateParam": template_param,
        "RegionId": "cn-hangzhou",
    }
    headers, qs = _v3_sign(
        "POST", host, query, "",
        Config.ALIYUN_SMS_ACCESS_KEY_ID,
        Config.ALIYUN_SMS_ACCESS_KEY_SECRET,
        action="SendSms", version="2017-05-25")
    try:
        r = requests.post("https://%s/?%s" % (host, qs),
                          headers=headers, timeout=15)
    except requests.RequestException as e:
        raise SMSError("短信网关连接失败：%s" % e)
    try:
        data = r.json()
    except ValueError:
        raise SMSError("短信网关返回异常：%s" % r.text[:200])
    if data.get("Code") != "OK":
        raise SMSError("短信发送失败：%s（%s）" % (
            data.get("Message"), data.get("Code")))
    return True


# ---------------- 对外接口 ----------------

def send_code(phone, purpose):
    """发送验证码。返回 {"dev_mode": bool, "code": 开发模式时返回}。"""
    import re as _re
    if purpose not in PURPOSES:
        raise SMSError("用途不对")
    if not _re.fullmatch(r"\d{11}", phone or ""):
        raise SMSError("手机号应为 11 位数字")
    s = _s()
    now = datetime.datetime.now()
    last = s.query(SmsCode).filter_by(
        phone=phone, purpose=purpose, del_flag=0).order_by(
        SmsCode.create_date.desc()).first()
    if last and (now - last.create_date).total_seconds() < RESEND_COOLDOWN_SECONDS:
        raise SMSError("发送太频繁，请 %s 秒后再试" % RESEND_COOLDOWN_SECONDS)
    code = "%06d" % random.randint(0, 999999)
    s.add(SmsCode(id=new_id(), phone=phone, code=code, purpose=purpose,
                  used=0,
                  expire_at=now + datetime.timedelta(minutes=CODE_TTL_MINUTES),
                  create_date=now))
    s.commit()
    if not sms_enabled():
        log.warning("[短信开发模式] %s 的 %s 验证码：%s", phone, purpose, code)
        return {"dev_mode": True, "code": code}
    import json as _json
    _send_sms_api(phone, _json.dumps({"code": code}, ensure_ascii=False))
    return {"dev_mode": False}


def verify_code(phone, code, purpose):
    """校验验证码。成功返回 True（并标记已用），失败抛 SMSError。"""
    if purpose not in PURPOSES:
        raise SMSError("用途不对")
    s = _s()
    now = datetime.datetime.now()
    row = s.query(SmsCode).filter_by(
        phone=phone, purpose=purpose, used=0, del_flag=0).order_by(
        SmsCode.create_date.desc()).first()
    if not row or row.code != (code or "").strip():
        raise SMSError("验证码不正确")
    if row.expire_at and row.expire_at < now:
        raise SMSError("验证码已过期，请重新获取")
    row.used = 1
    row.update_date = now
    s.commit()
    return True
