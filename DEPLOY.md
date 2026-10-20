# 家音部署与升级

从仓库根目录执行命令。以下统一使用 `/opt/memoir`，宝塔或其他路径请整体替换，不要再嵌套旧的原型目录名。

## 一、环境选择

| 环境 | 数据库 | 照片 | 运行 |
|---|---|---|---|
| 本地开发 | SQLite | 本地 `uploads/` | `python app.py`（调试模式） |
| 公网服务 | 显式配置 MySQL URL | 持久磁盘或 OSS 私有桶 | gunicorn + nginx + HTTPS |

Python 3.10+，推荐 3.12。已有 MySQL 建表文件以 5.7 语法为基线；数据库版本升级需在测试库验证，不能只改连接串就认定兼容。

`APP_ENV=cloud` 默认启用 OSS，**不会自动切换数据库**。`STORAGE_BACKEND=local` 可单独覆盖；使用本地磁盘时部署必须保留照片目录。

## 二、依赖与配置

将仓库放到 `/opt/memoir`，用运行服务的普通账号创建虚拟环境：

```bash
cd /opt/memoir
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
cp .env.example .env
chmod 600 .env
```

生产 `.env` 示例（占位符需替换）：

```dotenv
APP_ENV=cloud
SECRET_KEY=请替换为随机长字符串
DATABASE_URL=mysql+pymysql://memoir:URL编码后的密码@127.0.0.1:3306/memoir?charset=utf8mb4
STORAGE_BACKEND=oss
OSS_REGION=cn-hangzhou
OSS_BUCKET=你的私有桶
OSS_ACCESS_KEY_ID=从凭据系统填写
OSS_ACCESS_KEY_SECRET=从凭据系统填写
OSS_URL_EXPIRES=3600
```

密码中的特殊字符须按 URL 编码。密钥不要写进 Git、命令参数或日志。随机 SECRET_KEY 可用 `python3 -c 'import secrets; print(secrets.token_hex(32))'` 生成，保存到部署环境。

完整变量见 [.env.example](.env.example)：

- AI：`DEEPSEEK_API_KEY/BASE_URL/MODEL`，模型名按账户实际可用值配置；缺 key 则禁用。
- 短信：`ALIYUN_SMS_ACCESS_KEY_ID/ACCESS_KEY_SECRET/SIGN_NAME/TEMPLATE_CODE`；公网必须配好，缺配置会开启开发验证码模式。
- 本地照片：`UPLOAD_DIR` 建议绝对路径；OSS 可选 `OSS_ENDPOINT`，签名 URL 必须能被访问者网络访问，不要把仅服务器可达的内网域名用于浏览器展示。

OSS 桶设为私有。运行账号至少需要对象上传、读取和删除权限，分别对应 `oss:PutObject/GetObject/DeleteObject`。短期签名 URL 到期前仍可使用，成员移除不撤销已签发 URL。

## 三、新库初始化

新 SQLite 库由应用模型创建。新 MySQL 库先建空数据库，再导入根目录 SQL；示例使用 mysql 客户端交互输入密码：

```sql
CREATE DATABASE memoir CHARACTER SET utf8mb4;
```

```bash
mysql -h 127.0.0.1 -u memoir -p memoir < memoir-mysql-schema.sql
.venv/bin/python migrate.py
.venv/bin/python create_admin.py --phone 13800000000 --nickname 主持人 --family-name 我的家
```

业务表共 28 张，`schema_migrations` 由迁移程序维护。已有库不能重新导入建表 SQL。`create_admin.py` 交互输入密码，不清空已有记录；**生产不得执行 `seed.py`**。`install.sh` 是旧的演示安装入口，不用于已有数据库部署。

## 四、服务与 HTTPS

假设 `/opt/memoir` 归 `memoir` 服务账号所有，创建 `/etc/systemd/system/memoir.service`：

```ini
[Unit]
Description=Memoir Flask application
After=network.target

[Service]
User=memoir
WorkingDirectory=/opt/memoir
EnvironmentFile=/opt/memoir/.env
ExecStart=/opt/memoir/.venv/bin/gunicorn -w 3 -b 127.0.0.1:8000 app:app
Restart=always
UMask=0077

[Install]
WantedBy=multi-user.target
```

确认服务账号存在、可读配置和代码、可写本地照片目录，再执行：

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now memoir
```

nginx 代理示例：

```nginx
server {
    listen 80;
    server_name memoir.example.com;
    client_max_body_size 12m;
    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

替换域名、验证配置后签发 HTTPS 证书。安全组与防火墙开放 80/443；数据库端口仅向必要的内网服务开放。不要把本地 `uploads/` 配为 nginx 公开静态目录，否则会绕过应用权限。

宝塔同样使用项目虚拟环境：手动安装 `requirements.txt`，配置 gunicorn 绑定 127.0.0.1:8000，再配置站点反向代理与 SSL。面板是否自动安装依赖取决于插件配置，以实际环境检查为准。不要使用系统旧 Python，也不要对所有 gunicorn 服务统一执行 `pkill`。

## 五、已有部署升级

先备份数据库和照片，记录当前 Git 提交与环境配置位置；在测试库验证迁移及恢复。维护窗口内停止写入，再依次执行：

```bash
cd /opt/memoir
git pull --ff-only
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python migrate.py --dry-run
.venv/bin/python migrate.py
sudo systemctl restart memoir
```

迁移文件按文件名顺序执行并记录；新表由模型初始化创建，新列由迁移文件管理。不要改写已应用迁移，新增独立迁移文件。MySQL DDL 不保证事务回滚，失败时先核对实际表结构再恢复或继续，不能假设回滚 Git 就回滚了数据。

`.env`、SQLite 文件、本地照片及独立备份目录不受代码更新覆盖；备份必须另存，不只放同一块磁盘。生产恢复前先在隔离环境演练。

## 六、验收

- 不同家庭账号不能互读或修改；移除成员后无法再访问。
- 成员可看 public 故事，不能看其他人的草稿或私有故事。
- 照片上传、读取、删除正常；陌生账号和未登录者不能访问本地照片。
- 短信注册/找回使用真实验证码服务；AI 错误能被提示。
- 未发布分享返回 404，已发布分享需密码，下线后失效。
- 数据库和媒体备份存在，并已在独立目标验证恢复。

## 七、常见问题

- 照片 413：检查 nginx 上传大小，照片上限 10MB，可配置代理 12m。
- OSS 上传或删除失败：核对私有桶地域、凭据及对应操作权限。
- OSS 照片打不开：核对浏览器能访问的 endpoint、URL 有效期与桶配置。
- 模块找不到：检查实际 gunicorn 使用的虚拟环境，不能只在另一个 Python 中安装依赖。
- SQLite 与 MySQL 数据互迁：本仓库不提供自动跨引擎数据转换；需另行验证迁移方案，不能在已有数据上重灌 seed。
