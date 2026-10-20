# 部署文档（memoir-prototype）

一套代码，两种部署方式，用环境变量切换（见 `.env.example`）：

| 方式 | 适用 | 数据库 | 照片存储 | 启动 |
|---|---|---|---|---|
| 本地部署 | 自己电脑/内网演示 | SQLite（零配置） | 本地磁盘 `uploads/` | `python app.py` |
| 云部署 | 公网服务 | MySQL 5.7（RDS/自建） | 阿里云 OSS 私有桶 | gunicorn + systemd + nginx |
| 宝塔面板部署 | 装了宝塔面板的服务器 | 面板 MySQL 5.7 | 阿里云 OSS 私有桶 | Python项目管理器 / gunicorn |

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

用仓库根目录的建表 SQL 建表（27 张表，含审计字段；`persons` 表为树形结构）：

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

## 四、宝塔面板部署

> 适用：在装了宝塔面板的服务器上部署。面板可视化操作为主，少量终端命令。

### 4.1 软件商店安装运行环境

面板左侧「软件商店」→ 搜索安装：

- **Python 3.12**（运行环境分类）
- **MySQL 5.7**（数据库分类）
- **Nginx**（面板一般自带；没有就装一个）
- **phpMyAdmin**（可选，导入建表 SQL 用）

> ⚠️ 别用系统自带的 `python3`（一般是 3.8，`pip install` 会报找不到 Flask 3.1.0）。面板装的 Python 3.12 通常在 `/www/server/panel/pyenv/bin/python3.12`，不确定就跑 `find /www -name "python3.12" -type f` 确认。下面都用完整路径，记成 `PY312`。

### 4.2 传代码、建虚拟环境、装依赖

```bash
# 把 memoir-prototype 传到 /www/wwwroot/memoir（面板「文件」上传 zip 后解压，或 git clone）
cd /www/wwwroot/memoir/memoir-prototype

PY312=/www/server/panel/pyenv/bin/python3.12   # 按 4.1 找到的实际路径改
$PY312 -m venv venv
source venv/bin/activate
pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple
```

> 国内服务器建议加清华镜像（上面已带 `-i`），比官方源快很多。
> 如果 `$PY312 -m venv` 报错没有 venv 模块，先跑 `$PY312 -m pip install virtualenv`，再用 `virtualenv venv` 建。

### 4.3 数据库：建库 + 导表

1. 面板左侧「数据库」→「添加数据库」：库名 `memoir`，字符集选 `utf8mb4`，记下用户名和密码。
2. 导入建表 SQL：点该数据库的「管理」进 phpMyAdmin →「导入」→ 选择 `memoir-mysql-schema.sql` → 执行。27 张表一次建完。

### 4.4 环境变量

在项目目录（`/www/wwwroot/memoir/memoir-prototype/`）新建 `.env`，对照 `.env.example` 填，关键几项：

```bash
APP_ENV=cloud
SECRET_KEY=换成32位以上随机字符串
DATABASE_URL=mysql+pymysql://用户名:密码@127.0.0.1:3306/memoir?charset=utf8mb4
STORAGE_BACKEND=oss
OSS_REGION=cn-hangzhou
OSS_BUCKET=memoir-photos
OSS_ACCESS_KEY_ID=xxx
OSS_ACCESS_KEY_SECRET=xxx
# 短信 / DeepSeek 按需填，不填对应功能自动隐藏或走开发模式
```

> `.env` 不要进 git；AK 用 RAM 子账号。

生产初始化管理员（不要跑 `seed.py`，它会清空表）：

```bash
source venv/bin/activate
python create_admin.py --phone 13800000000 --nickname 主持人 --family-name 王家
```

### 4.5 启动服务（二选一）

**A. Python项目管理器（可视化，推荐）**

1. 软件商店搜索安装「Python项目管理器」插件。
2. 插件里「添加项目」：项目路径选 `/www/wwwroot/memoir/memoir-prototype`，Python 版本选 3.12，按向导填启动文件（`app.py`）和端口（如 8000）。
3. 插件会自动建虚拟环境、装依赖、以后台守护进程运行，开机自启。

**B. 终端手动（gunicorn）**

```bash
source venv/bin/activate
nohup gunicorn -w 3 -b 127.0.0.1:8000 app:app > gunicorn.log 2>&1 &
```

> 生产建议配成守护进程（用上面的 Python项目管理器，或按 3.7 写 systemd service，把路径换成面板路径）。

### 4.6 反向代理 + HTTPS（面板可视化）

1. 面板左侧「网站」→「添加站点」：域名填你的（如 `memoir.example.com`），FTP/数据库都不建，PHP 版本选「纯静态」。
2. 点站点「设置」→「反向代理」→「添加反向代理」：目标 URL 填 `http://127.0.0.1:8000`（与 4.5 的端口一致），保存。
3. 「设置」→「SSL」→「Let's Encrypt」→ 申请证书，开启「强制 HTTPS」。
4. 照片上传上限 10MB：反向代理的配置文件里确认有 `client_max_body_size 12m;`，没有就加上后保存。

### 4.7 端口放行（两个地方都要放）

- 面板左侧「安全」→ 放行 **80** 和 **443**。
- 云服务器控制台（阿里云 ECS 安全组）→ 同样放行 80/443。缺一个都访问不了。

### 4.8 上线检查清单

- [ ] 首页/家族树/故事页可打开
- [ ] 登录后可写文章、传照片（照片能显示 → OSS 签名 URL 有效）
- [ ] 注册短信验证码能收到（生产需配好阿里云短信 AK/签名/模板）
- [ ] 分享页 token+密码可访问
- [ ] `SECRET_KEY` 已换成随机值

### 4.9 代码更新流程（每次更新固定三步）

```bash
cd /www/wwwroot/family.scyllatech.cn/memoir-prototype   # 按实际项目路径改
git pull
/www/server/pyporject_evn/memoir-prototype_venv/bin/python migrate.py
# 面板「Python 项目管理器」里重启项目（若 gunicorn 有残留进程，先 pkill -f gunicorn 杀干净再重启）
```

说明：
- `migrate.py` 自动补齐 `migrations/` 里新增的表结构变更（读 `.env` 的 `DATABASE_URL`，直连 MySQL），
  已手动执行过的变更会自动跳过，重复跑是安全的；可用 `--dry-run` 先看会执行哪些。
- 不用再记零散的 ALTER：以后每次代码更新若有表结构变化，只会多一个 `migrations/00N_xxx.sql` 文件。
- ⚠️ 仍然不要跑 `python seed.py`（它会清空 16 张表再灌演示数据，见 FAQ）。

---

## 五、环境变量总表

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

## 六、FAQ

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

**Q：宝塔终端 pip install 报找不到 Flask==3.1.0？**
A：用的是系统自带的 Python 3.8（Flask 3.1.0 要求 3.9+）。改用面板装的 Python 3.12 完整路径建 venv（见 4.1–4.2），不要动系统 python3。

**Q：宝塔 Python项目管理器启动报 `ModuleNotFoundError: No module named 'flask'`？**
A：项目管理器只建虚拟环境，不自动装 `requirements.txt`。用项目 venv 自带的 pip 手动装（路径按实际改）：

```bash
/www/server/pyporject_evn/<项目名>_venv/bin/pip install -r /www/wwwroot/<站点>/memoir-prototype/requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple
```

装完在项目管理器里重启项目。以后 requirements 加了新依赖，也要手动跑一遍这条。

**Q：正式版微信登录怎么接？**
A：原型是手机号+密码；正式版按架构（微信登录+手机号双绑定）替换 `/login` 逻辑，`users.wechat_openid` 字段已预留。
