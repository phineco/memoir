# 部署文档（memoir-prototype）

一套代码，两种部署方式，用环境变量切换（见 `.env.example`）：

| 方式 | 适用 | 数据库 | 照片存储 | 启动 |
|---|---|---|---|---|
| 本地部署 | 自己电脑/内网演示 | SQLite（零配置） | 本地磁盘 `uploads/` | `python app.py` |
| 云部署 | 公网服务 | MySQL 5.7（RDS/自建） | 阿里云 OSS 私有桶 | gunicorn + systemd + nginx |

---

## 一、环境要求

- Python 3.10+（推荐 3.11/3.12）
- 本地部署：无其他依赖
- 云部署：MySQL 5.7、阿里云 OSS Bucket（建议私有桶）、域名（可选，用于 HTTPS）

---

## 二、本地部署（5 分钟）

```bash
cd memoir-prototype
python3 -m venv venv && source venv/bin/activate   # 可选，但推荐
pip install -r requirements.txt

python seed.py    # 灌演示数据（王家/4 人物/2 故事；会清空表，仅演示用）
python app.py     # http://localhost:5000
```

演示账号：`13800000000` / `demo123`（含一篇示例草稿，可体验草稿箱）。

> 局域网给家人看：`python app.py` 已监听 `0.0.0.0`，把本机 IP 发给家人即可（如 `http://192.168.1.10:5000`）。

---

## 三、云部署（以阿里云 ECS + Ubuntu 为例）

### 3.1 服务器准备

- ECS（2核4G 起）、安全组放行 80/443（以及 SSH）
- （可选）RDS MySQL 5.7；或 ECS 本机装 MySQL 5.7

```bash
sudo apt update && sudo apt install -y python3 python3-venv python3-dev \
  default-libmysqlclient-dev nginx certbot python3-certbot-nginx
```

### 3.2 拉代码、装依赖

```bash
mkdir -p /opt/memoir && cd /opt/memoir
# 把 memoir-prototype 目录传到服务器（scp / git）
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt
```

### 3.3 MySQL 建库建表

```sql
CREATE DATABASE memoir CHARACTER SET utf8mb4;
```

用仓库根目录的建表 SQL 建表（19 张表，含审计字段；`persons` 表为树形结构）：

```bash
mysql -h <host> -u <user> -p memoir < /path/to/memoir-mysql-schema.sql
```

> 建表 SQL 在 `your_files/memoir-mysql-schema.sql`（与 `memoir-website-architecture.md` 的表清单一一对应）。

### 3.4 OSS Bucket 与 RAM 授权

1. OSS 控制台建 Bucket：**私有**读写权限（照片走签名 URL 访问，架构已定此方案），地域与 ECS 同地域（如 `cn-hangzhou`，走内网更快更省）。
2. RAM 控制台建子账号，只授两个权限（最小化）：
   - `oss:PutObject`（上传）
   - `oss:GetObject`（生成签名 URL 下载）
3. 记下：`OSS_REGION`（如 `cn-hangzhou`）、`OSS_BUCKET`、AK / SK。

> 内网访问可配 `OSS_ENDPOINT=oss-cn-hangzhou-internal.aliyuncs.com`（同地域 ECS 免公网流量）。

### 3.5 环境变量

```bash
cat > /opt/memoir/.env <<'EOF'
APP_ENV=cloud
SECRET_KEY=换成32位以上随机字符串
DATABASE_URL=mysql+pymysql://memoir:密码@127.0.0.1:3306/memoir?charset=utf8mb4
STORAGE_BACKEND=oss
OSS_REGION=cn-hangzhou
OSS_BUCKET=memoir-photos
OSS_ENDPOINT=oss-cn-hangzhou-internal.aliyuncs.com
OSS_ACCESS_KEY_ID=xxx
OSS_ACCESS_KEY_SECRET=xxx
OSS_URL_EXPIRES=3600
EOF
```

用 systemd 时在 service 文件里 `EnvironmentFile=/opt/memoir/.env`；或用 supervisor/docker 自行加载。

> ⚠️ `.env` 不要进 git；AK 用 RAM 子账号，不要用主账号。

### 3.6 初始化管理员（不要跑 seed.py）

`seed.py` 会清空所有表，仅演示用。生产用：

```bash
source venv/bin/activate
python create_admin.py --phone 13800000000 --nickname 主持人 --family-name 王家
# 交互输入密码（≥6 位）；会自动建家庭并设为创建者(owner)
```

之后在网页「成员管理」里把家人加为管理员/成员。

### 3.7 gunicorn + systemd

`/etc/systemd/system/memoir.service`：

```ini
[Unit]
Description=memoir flask app
After=network.target

[Service]
User=www-data
WorkingDirectory=/opt/memoir/memoir-prototype
EnvironmentFile=/opt/memoir/.env
ExecStart=/opt/memoir/venv/bin/gunicorn -w 3 -b 127.0.0.1:8000 app:app
Restart=always

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now memoir
sudo systemctl status memoir
```

> `-w 3`：3 个 worker；小规模家庭够用。`app:app` 对应 `app.py` 里的 `app` 对象。

### 3.8 nginx 反向代理 + HTTPS

`/etc/nginx/sites-available/memoir`：

```nginx
server {
    listen 80;
    server_name memoir.example.com;

    client_max_body_size 12m;   # 照片上传上限 10MB，留余量

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

```bash
sudo ln -s /etc/nginx/sites-available/memoir /etc/nginx/sites-enabled/
sudo nginx -t && sudo systemctl reload nginx
# HTTPS（一行搞定）
sudo certbot --nginx -d memoir.example.com
```

### 3.9 上线检查清单

- [ ] 首页/家族树/故事页可打开
- [ ] 登录后可写文章、传照片（照片能显示 → OSS 签名 URL 有效）
- [ ] 分享页 token+密码可访问
- [ ] `SECRET_KEY` 已换成随机值（默认 `dev-secret-key-change-me` 不可用于生产）
- [ ] MySQL/RDS 备份策略已开

---

## 四、环境变量总表

| 变量 | 默认 | 说明 |
|---|---|---|
| `APP_ENV` | `local` | `local` 本地部署 / `cloud` 云环境 |
| `DATABASE_URL` | `sqlite:///memoir.db` | 生产示例见 3.5 |
| `SECRET_KEY` | `dev-secret-key-change-me` | 生产必须换 |
| `STORAGE_BACKEND` | 跟随 `APP_ENV` | `local` 本地磁盘 / `oss` 阿里云 OSS |
| `UPLOAD_DIR` | `./uploads` | local 模式存储目录（持久化磁盘） |
| `OSS_REGION` | — | 如 `cn-hangzhou` |
| `OSS_BUCKET` | — | 私有桶名 |
| `OSS_ENDPOINT` | — | 可选；同地域 ECS 建议内网 endpoint |
| `OSS_ACCESS_KEY_ID` / `OSS_ACCESS_KEY_SECRET` | — | RAM 子账号 AK |
| `OSS_URL_EXPIRES` | `3600` | 签名 URL 有效秒数 |
| `DEEPSEEK_API_KEY` | （空） | DeepSeek key；为空则 AI 问答/周报导读功能隐藏 |
| `DEEPSEEK_BASE_URL` | `https://api.deepseek.com` | 兼容 OpenAI 接口地址 |
| `DEEPSEEK_MODEL` | `deepseek-flash` | 模型名 |
| `ALIYUN_SMS_ACCESS_KEY_ID` / `ALIYUN_SMS_ACCESS_KEY_SECRET` | （空） | 阿里云短信 AK；为空则开发模式 |
| `ALIYUN_SMS_SIGN_NAME` | （空） | 短信签名（如：家音） |
| `ALIYUN_SMS_TEMPLATE_CODE` | （空） | 短信模板 Code（需含 ${code} 变量） |

---

## 五、FAQ

**Q：照片传成功但打不开？**
A：① 检查 bucket 是否私有——私有是对的，页面用签名 URL；② 检查 `OSS_URL_EXPIRES` 是否太短；③ RAM 账号是否有 `oss:GetObject` 权限；④ ECS 与 bucket 是否同地域、endpoint 是否写对。

**Q：上传报 "OSS 未配置完整"？**
A：`STORAGE_BACKEND=oss` 但 AK/SK/region/bucket 没配全。对照 `.env.example` 补齐后重启服务（systemd：`sudo systemctl restart memoir`）。

**Q：上传大照片报 413？**
A：nginx `client_max_body_size` 太小，按 3.8 改到 12m 后 reload。

**Q：MySQL 连不上？**
A：① 安全组放行 3306（只对 ECS 内网段）；② `DATABASE_URL` 里 `pymysql` 驱动名别写错；③ 先 `mysql -h ... -u ... -p` 手动连通再排查应用。

**Q：从 SQLite 迁到 MySQL，数据怎么办？**
A：原型阶段建议重灌（`memoir-mysql-schema.sql` 建表 + `create_admin.py` 建号）；历史演示数据如需保留，用 SQLite→MySQL 迁移工具（如 `sqlite3 .dump` 手工调）另行处理，不在本文范围。

**Q：正式版微信登录怎么接？**
A：原型是手机号+密码；正式版按架构（微信登录+手机号双绑定）替换 `/login` 逻辑，`users.wechat_openid` 字段已预留。
