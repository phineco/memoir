"""配置：全部走环境变量，一套代码跑本地和云。

运行环境开关：
  APP_ENV=local   本地部署（默认）：SQLite + 本地磁盘存照片
  APP_ENV=cloud   云环境：MySQL + 阿里云 OSS 私有桶（签名 URL 访问）

也可单独覆盖存储后端：STORAGE_BACKEND=local|oss（默认跟随 APP_ENV）。
OSS 配置见 .env.example。
"""
import os

from dotenv import load_dotenv

_BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# 自动加载项目目录下的 .env（环境变量已设置时优先用环境变量）
load_dotenv(os.path.join(_BASE_DIR, ".env"))


class Config:
    DATABASE_URL = os.environ.get("DATABASE_URL", "sqlite:///memoir.db")
    SECRET_KEY = os.environ.get("SECRET_KEY", "dev-secret-key-change-me")
    APP_TIMEZONE = os.environ.get("APP_TIMEZONE", "Asia/Shanghai")

    # ---- 环境开关 ----
    APP_ENV = os.environ.get("APP_ENV", "local")  # local | cloud
    STORAGE_BACKEND = os.environ.get(
        "STORAGE_BACKEND",
        "oss" if os.environ.get("APP_ENV") == "cloud" else "local",
    )  # local | oss

    # ---- 本地存储（STORAGE_BACKEND=local） ----
    UPLOAD_DIR = os.environ.get("UPLOAD_DIR", os.path.join(_BASE_DIR, "uploads"))

    # ---- 阿里云 OSS（STORAGE_BACKEND=oss），SDK v2 ----
    OSS_REGION = os.environ.get("OSS_REGION", "")            # 如 cn-hangzhou
    OSS_BUCKET = os.environ.get("OSS_BUCKET", "")            # 私有桶名
    OSS_ENDPOINT = os.environ.get("OSS_ENDPOINT", "")        # 可选，如 oss-cn-hangzhou.aliyuncs.com
    OSS_ACCESS_KEY_ID = os.environ.get("OSS_ACCESS_KEY_ID", "")
    OSS_ACCESS_KEY_SECRET = os.environ.get("OSS_ACCESS_KEY_SECRET", "")
    OSS_URL_EXPIRES = int(os.environ.get("OSS_URL_EXPIRES", "3600"))  # 签名 URL 有效秒数

    # ---- AI（DeepSeek，预置提示词直调） ----
    DEEPSEEK_API_KEY = os.environ.get("DEEPSEEK_API_KEY", "")
    DEEPSEEK_BASE_URL = os.environ.get(
        "DEEPSEEK_BASE_URL", "https://api.deepseek.com")
    DEEPSEEK_MODEL = os.environ.get("DEEPSEEK_MODEL", "deepseek-flash")
    AI_ENABLED = bool(os.environ.get("DEEPSEEK_API_KEY", ""))

    # ---- 阿里云短信（Dysmsapi SendSms） ----
    ALIYUN_SMS_ACCESS_KEY_ID = os.environ.get("ALIYUN_SMS_ACCESS_KEY_ID", "")
    ALIYUN_SMS_ACCESS_KEY_SECRET = os.environ.get("ALIYUN_SMS_ACCESS_KEY_SECRET", "")
    ALIYUN_SMS_SIGN_NAME = os.environ.get("ALIYUN_SMS_SIGN_NAME", "")
    ALIYUN_SMS_TEMPLATE_CODE = os.environ.get("ALIYUN_SMS_TEMPLATE_CODE", "")
    ALIYUN_SMS_ENDPOINT = os.environ.get(
        "ALIYUN_SMS_ENDPOINT", "dysmsapi.aliyuncs.com")
    SMS_ENABLED = bool(os.environ.get("ALIYUN_SMS_ACCESS_KEY_ID", "")
                       and os.environ.get("ALIYUN_SMS_SIGN_NAME", "")
                       and os.environ.get("ALIYUN_SMS_TEMPLATE_CODE", ""))
