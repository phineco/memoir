"""存储后端抽象。

- local：存到本地磁盘 UPLOAD_DIR，读取走 /uploads/<key>（原型/本地部署）。
- oss：阿里云 OSS 私有桶（SDK v2），上传用 put_object，读取用带过期时间的
  签名 URL（presign GetObject），key 不暴露给外部。

切换：环境变量 STORAGE_BACKEND=local|oss（默认跟随 APP_ENV）。
"""
import datetime
import os


class StorageBackend:
    def save(self, data: bytes, key: str) -> str:
        """保存 bytes，返回存储标识（存 photos.storage_path）。"""
        raise NotImplementedError

    def delete(self, key: str) -> None:
        """删除对象（不存在也不报错）。"""
        raise NotImplementedError

    def read(self, key: str, limit: int) -> bytes:
        """Read private bytes without issuing a browser storage URL."""
        raise NotImplementedError

    def url(self, key: str) -> str:
        """返回可在 <img> 里直接用的访问 URL。"""
        raise NotImplementedError


class LocalStorageBackend(StorageBackend):
    def __init__(self, upload_dir):
        self.upload_dir = upload_dir

    def save(self, data: bytes, key: str) -> str:
        dest = os.path.join(self.upload_dir, key)
        os.makedirs(os.path.dirname(dest), exist_ok=True)
        with open(dest, "wb") as fh:
            fh.write(data)
        return key

    def delete(self, key: str) -> None:
        dest = os.path.join(self.upload_dir, key)
        if os.path.isfile(dest):
            os.remove(dest)

    def read(self, key: str, limit: int) -> bytes:
        from pathlib import Path
        root=Path(self.upload_dir).resolve();path=(root/key).resolve()
        if root not in path.parents or path.is_symlink():raise ValueError('invalid storage key')
        with path.open('rb') as stream:return stream.read(limit)

    def url(self, key: str) -> str:
        if key and key.startswith('voice/'):return ''
        return f"/uploads/{key}"


class OssStorageBackend(StorageBackend):
    """阿里云 OSS（Python SDK v2）：私有桶 + 签名 URL。"""

    def __init__(self, region, bucket, access_key_id, access_key_secret,
                 endpoint="", url_expires=3600):
        missing = [n for n, v in [
            ("OSS_REGION", region), ("OSS_BUCKET", bucket),
            ("OSS_ACCESS_KEY_ID", access_key_id),
            ("OSS_ACCESS_KEY_SECRET", access_key_secret),
        ] if not v]
        if missing:
            raise RuntimeError(
                "OSS 未配置完整，缺失：" + "、".join(missing)
                + "（见 .env.example，设置环境变量后重启）")
        try:
            import alibabacloud_oss_v2 as oss
        except ImportError:
            raise RuntimeError(
                "未安装 alibabacloud-oss-v2：pip install alibabacloud-oss-v2")
        cfg = oss.config.load_default()
        cfg.credentials_provider = oss.credentials.StaticCredentialsProvider(
            access_key_id, access_key_secret)
        cfg.region = region
        if endpoint:
            cfg.endpoint = endpoint
        self._oss = oss
        self.client = oss.Client(cfg)
        self.bucket = bucket
        self.url_expires = url_expires

    def save(self, data: bytes, key: str) -> str:
        result = self.client.put_object(self._oss.PutObjectRequest(
            bucket=self.bucket, key=key, body=data))
        if result.status_code != 200:
            raise RuntimeError(f"OSS 上传失败，状态码 {result.status_code}")
        return key

    def delete(self, key: str) -> None:
        self.client.delete_object(self._oss.DeleteObjectRequest(
            bucket=self.bucket, key=key))

    def read(self, key: str, limit: int) -> bytes:
        result=self.client.get_object(self._oss.GetObjectRequest(bucket=self.bucket,key=key))
        try:return result.body.read(limit)
        finally:result.body.close()

    def url(self, key: str) -> str:
        if key and key.startswith('voice/'):return ''
        r = self.client.presign(
            self._oss.GetObjectRequest(bucket=self.bucket, key=key),
            expires=datetime.timedelta(seconds=self.url_expires))
        return r.url


_backend = None


def get_storage() -> StorageBackend:
    """按配置返回存储后端（单例）。"""
    global _backend
    if _backend is None:
        from config import Config
        if Config.STORAGE_BACKEND == "oss":
            _backend = OssStorageBackend(
                region=Config.OSS_REGION, bucket=Config.OSS_BUCKET,
                access_key_id=Config.OSS_ACCESS_KEY_ID,
                access_key_secret=Config.OSS_ACCESS_KEY_SECRET,
                endpoint=Config.OSS_ENDPOINT,
                url_expires=Config.OSS_URL_EXPIRES)
        else:
            _backend = LocalStorageBackend(Config.UPLOAD_DIR)
    return _backend


def storage_url(key: str) -> str:
    if key and key.startswith('album/'):
        import re
        from flask import url_for
        match=re.fullmatch(r'album/([A-Za-z0-9_-]{1,64})/([a-f0-9]{32})\.(?:jpg|png)',key)
        return url_for('album.image',family_id=match[1],photo_id=match[2]) if match else ''
    if key and key.startswith('voice/'):return ''
    return get_storage().url(key)
