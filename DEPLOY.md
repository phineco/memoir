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

应用启动只配置数据库连接，不执行建表或迁移，避免多个 gunicorn worker 同时建表。初始化和迁移都须在服务停止时由一个进程执行。

新 SQLite 库先显式初始化，再执行迁移并创建账号：

```bash
.venv/bin/python init_db.py
.venv/bin/python migrate.py
.venv/bin/python create_admin.py --phone 13800000000 --nickname 主持人 --family-name 我的家
```

`init_db.py` 检测到已有表会拒绝，避免将新库初始化误用于已有资料。已有库直接走第五节增量升级。

新 MySQL 库先建空数据库，再导入根目录 SQL；示例使用 mysql 客户端交互输入密码：

```sql
CREATE DATABASE memoir CHARACTER SET utf8mb4;
```

```bash
mysql -h 127.0.0.1 -u memoir -p memoir < memoir-mysql-schema.sql
.venv/bin/python migrate.py
.venv/bin/python create_admin.py --phone 13800000000 --nickname 主持人 --family-name 我的家
```

业务表共 31 张，`schema_migrations` 由迁移程序维护。已有库不能重新导入建表 SQL。`create_admin.py` 交互输入密码，不清空已有记录；**生产不得执行 `seed.py`**。`install.sh` 只建立项目虚拟环境、安装依赖和缺省配置，不再自动执行 seed 或修改数据库。

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
Environment=TZ=Asia/Shanghai
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

先按 [备份与恢复演练](BACKUP.md) 备份数据库和照片，记录当前 Git 提交与环境配置位置；在测试库验证迁移及恢复。维护窗口内停止服务（宝塔先在面板停止本项目），确认旧 worker 已退出，再依次执行：

```bash
cd /opt/memoir
sudo systemctl stop memoir
git pull --ff-only
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python migrate.py --dry-run
.venv/bin/python migrate.py
sudo systemctl start memoir
```

`--dry-run` 只读预演，不建数据库或迁移记录表。周报当前年周按 `APP_TIMEZONE`（默认 Asia/Shanghai），服务 `TZ` 须与之相同；旧无时区时间需核对后再调整。

迁移文件按文件名顺序执行并记录；已有库的新增表和列都由迁移文件管理，不能依赖启动时自动补表。不要改写已应用迁移，新增独立迁移文件；不要同时启动多个迁移程序。MySQL DDL 不保证事务回滚，失败时先核对实际表结构再恢复或继续，不能假设回滚 Git 就回滚了数据。

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
- 启动报 `1050 Table 'ai_turns' already exists`：旧版 worker 启动时同时执行 `create_all`，可能发生先检查后创建的竞争。保留现有表和数据，先停止本项目、备份，更新修复后的代码，单独执行 `migrate.py --dry-run` 与 `migrate.py`，确认成功后再启动。不要删除 `ai_turns`、重导全库 SQL 或运行 seed。迁移对已存在的新表使用 `CREATE TABLE IF NOT EXISTS`；如果旧启动过程留下的是不完整结构，应先核对字段和索引，不能直接删除重建。

## 八、UI 构建与版本发布（推荐更新方式）

2026-10-20 的四步 UI 改造不涉及数据库结构迁移；2026-10-21 的人物双历日期功能需要执行第九节迁移。Tailwind 与测试工具只在开发机/CI 运行，生产接收 Python 源码及 `static/dist/`。ECharts、Quill 和字体均不依赖运行时外网下载；字体使用设备字体。

开发或 CI：

```bash
python tools/frontend.py bootstrap
python tools/frontend.py build
python tools/frontend.py check
python -m pytest -q
npm ci --ignore-scripts
npx playwright install --with-deps chromium
UI_BROWSER_CHANNEL=chromium UI_SCREENSHOTS=ui-artifacts python tools/run_ui.py
python tools/frontend.py release --version ui-20261020 --output dist/memoir-ui-20261020.tar.gz
```

工具下载与依赖安装需要网络；已有固定版本 Tailwind 工具可通过 `TAILWIND_BIN` 指定，执行前校验官方哈希。Python 依赖仍按 `requirements.txt` 安装，本轮未更换后端版本。CI 在 SQLite、MySQL 和 UI 回归均通过后生成发布包、校验清单和截图，上传为 Actions artifacts；不自动部署。

`release` 只打包允许的源码与静态资源，记录文件 SHA-256 到 `RELEASE.json`，排除 `.env`、数据库、照片、虚拟环境和备份。发布前必须执行 `check` 与测试；`release` 会再检查依赖和静态文件完整性。不要把发布包当作数据备份。

建议生产目录：

```text
/opt/memoir/
  current -> releases/memoir-ui-20261020
  releases/                  每个版本一份代码和独立 .venv
  shared/.env                配置与密钥
  shared/uploads/            本地照片（若使用）
  shared/memoir.db            SQLite（若使用）
  shared/static/             历次带指纹资源，累积保留
```

首次转到此结构，先备份并由管理员迁入原配置/资料，再确认配置中的 `DATABASE_URL` 与 `UPLOAD_DIR` 是稳定的绝对路径。MySQL 或 OSS 的现有存储位置不变。应用启动前配置好 `shared/.env`，不能用发布包覆盖。

在服务器核对下载的 `SHA256SUMS` 后解包到 `releases/`；以下示例中的版本名要换为实际值：

```bash
cd /opt/memoir
sha256sum -c SHA256SUMS
mkdir -p releases shared/static
tar -xzf memoir-ui-20261020.tar.gz -C releases
release_dir=/opt/memoir/releases/memoir-ui-20261020
python3 "$release_dir/tools/frontend.py" verify-release
ln -s /opt/memoir/shared/.env "$release_dir/.env"
python3 -m venv "$release_dir/.venv"
"$release_dir/.venv/bin/python" -m pip install -r "$release_dir/requirements.txt"
cp "$release_dir"/static/dist/*.css "$release_dir"/static/dist/*.js /opt/memoir/shared/static/
```

systemd 中将 `WorkingDirectory` 改为 `/opt/memoir/current`、`EnvironmentFile` 改为 `/opt/memoir/shared/.env`、`ExecStart` 改为 `/opt/memoir/current/.venv/bin/gunicorn -w 3 -b 127.0.0.1:8000 app:app`。nginx 增加以下规则，使发布切换中的旧页面仍能加载旧指纹资源：

```nginx
location ~ ^/static/dist/(.+\.[0-9a-f]{16}\.(?:css|js))$ {
    alias /opt/memoir/shared/static/$1;
    add_header Cache-Control "public, max-age=31536000, immutable";
}
```

HTML 由应用返回 `no-store`；缓存只针对带指纹的 CSS/JS，修改内容会生成新地址。使用 Flask 静态资源而未配置 nginx 规则时仍可运行，但跨版本请求的旧文件需自行保留。共享指纹目录至少保留回滚窗口内的资源。

准备完成后，记录旧 `current` 目标，在维护窗口执行 Linux 原子链接切换与服务重启：

```bash
ln -s releases/memoir-ui-20261020 /opt/memoir/current.next
mv -Tf /opt/memoir/current.next /opt/memoir/current
sudo systemctl daemon-reload
sudo systemctl restart memoir
```

在实际域名检查登录、读故事、保存草稿、家庭管理和手机大字模式。若本次 UI 发布异常，将上面链接指向已记录的旧版本，原子替换并重启；配置、数据库和照片始终留在 `shared`。保留旧版本 `.venv` 和静态资源，不需重新安装或还原数据。未来含数据库迁移的发布必须另行评估回滚，不能仅切代码。


## 九、人物双历日期升级（2026-10-21）

此版本新增 `002_person_dual_calendar_dates.sql`，在 `persons` 表增加 12 个可空的年/月/日字段和 2 个农历闰月标记。出生、去世的公历与农历分别保存；旧 `birth_year/death_year` 及历法字段仍保留供兼容读取，主年份优先公历、其次农历。

迁移仅把旧年份复制到其原历法的新增年份字段，不换算另一历法，不补月日、不删除旧资料。未知年份的月日也可保留；农历只检查字段范围，不自动核验实际闰月或两套日期是否对应，需由家人核实。

已有库升级：先完成独立数据库/媒体备份及恢复验证，停止写入和旧服务，在新版本目录建立虚拟环境和 `.env` 链接，再执行：

```bash
.venv/bin/python migrate.py --dry-run
.venv/bin/python migrate.py
```

上述命令使用当前版本目录的配置。预演核对目标库后再正式迁移；完成后再切换 `current` 并重启服务。不要在已有库重新导入建表 SQL，也不要运行 `seed.py`。MySQL DDL 失败时应核对实际列状态后重试，迁移会跳过已有列；只有完整成功才记录版本。

验收：旧公历/农历年份仍正确，新建人物分别只填一套或两套日期均能保存，编辑回填与清空正确，健在和去世日期不能同时提交。迁移中的旧记录月日应仍为空。

新增列可以保留，不能通过删列回滚。若需退回旧程序，先停止相关写入并保留备份；旧界面仅能维护年份，在旧版继续改生卒年份可能与新增日期脱节，须人工核对后再恢复写入。


## 十、公开邀请地址和二维码

`PUBLIC_BASE_URL` 是公开站点的协议与域名，默认 `https://family.scyllatech.cn`。反向代理内的 `127.0.0.1:443`、Host 和 X-Forwarded-Host 不参与邀请地址生成；域名变更时只更新此环境变量并重启。值不能包含账号、路径、查询或片段。

更新后先安装 `requirements.txt`（包含固定版本纯 Python 二维码依赖），再重启应用，无需增加数据库迁移。既有邀请码不变，管理页会按当前公开域名重建链接，旧会话中缓存的内网地址也不再展示。

新建邀请同时显示二维码，历史有效邀请也可预览和下载 PNG。二维码由本站生成，管理员权限、家庭隔离及邀请的有效期/使用次数继续生效；预览或下载不会消耗邀请次数，也不会延长原邀请。二维码图片不经第三方接口、不写入公开静态目录，接口响应不缓存。

## 协议与隐私政策

- `/terms`、`/privacy` 可匿名阅读；页脚、注册、登录及个人中心提供入口。
- 正式上线前设置 `PRIVACY_CONTACT_EMAIL` 为真实可用且有人处理的邮箱，并核实运营主体、实际存储地域及 AI / 短信 / 存储供应商；当前文本不能代替具体场景所需的单独授权和法律审查。
- 更新前先备份，再执行 `python migrate.py`（新增 003 协议确认表）。自行注册确认同时记录双方文件版本与 UTC 时间，不回填已有用户或代开账号的同意。
- 修改协议正文时，同时更新 `legal.py` 中相应版本，保留已发布版本的 Git 历史；旧版本表单会要求重新查看确认。现有账号的重新征求同意、敏感信息与儿童授权不在此次页面交付中。
- 账号注销和复杂删除目前通过联系邮箱人工核验；运营方应落实处理流程、存储地域告知、日志/备份清理期限及第三方约定，页面不代表已经提供自动删除能力。


## MySQL 断线与连接池（2006 / Broken pipe）

若页面查询出现 `MySQL server has gone away`，通常应检查空闲超时、数据库重启、网络断开等原因。应用在取用池中连接前执行存活校验，失效时先换连接再执行业务查询；MySQL 连接默认在使用超过 1800 秒后于下次取用时回收。可在 `.env` 设置正整数 `DB_POOL_RECYCLE_SECONDS`，使其小于数据库实际 `wait_timeout`；不需要修改数据库参数来启用此修复。SQLite 不按时长回收，以保护内存库。

更新本次代码后，重启宝塔 Python 项目或对应 Gunicorn / systemd 应用进程，使新连接池配置生效。本修复不涉及表结构变更，无需为此额外执行迁移，也不需要清理家庭资料。

校验：进入帮助页或家庭页面，空闲后再次访问仍正常；若持续断连，检查 MySQL 进程、服务日志、可用连接数及应用到数据库的网络。存活校验不能修复数据库本身不可用，也不能保证事务执行中途不断线；写入中断时不自动重放保存操作，应先核对是否已保存后再处理，避免重复数据。

参考：[SQLAlchemy 连接池断线处理](https://docs.sqlalchemy.org/en/20/core/pooling.html#disconnect-handling-pessimistic)。

## 2026-10-22 人物状态升级

已有库先执行 `python migrate.py` 完成 004，再启动新版。迁移仅增加可空状态字段，不覆写历史生卒信息；旧非健在且无死亡资料的记录展示为待核实。回退旧程序前停写并核对新增未知状态，旧程序无法表达三种状态，不可直接删列。

## 一次性账号结果

代开及重置密码的结果在服务器私有临时目录保存，五分钟内可读取一次；客户端仅保留随机引用。目录默认位于系统临时目录，按应用路径隔离，目录权限 0700、文件 0600；结果读取后删除，过期文件在后续操作时清理。该目录不纳入家庭资料备份。单机 Gunicorn 多进程可共享；多实例部署须将 `ACCOUNT_NOTICE_DIR` 指向同一安全共享目录，或在上线前替换为集中式短期存储。结果丢失或过期时重新设置密码，不回查明文。

## 故事修订与核实

新增 005 家人修正建议表，启动新版前执行迁移。发布后修订保留正文版本和修改原因；采纳建议与保存新版本在同一事务完成。历史版本只向可编辑此故事的人开放，管理员不能借此查看私人故事。对外快照不随修订自动更新。

## 首次发布时间

执行 006 增加可空的首次发布时间。旧资料不回填不可靠时间，周报按原录入时间推定并标注；新发布与同步录入写入实际首次发布时间，后续修订不改变归周。周报另列本周修订动态，不公开历史正文。

## AI 请求与证据

执行 007 增加 AI 请求状态表后再启动新版。请求编号按用户与家庭隔离，重复编号不重复调用模型，成功结果可复用；失败、取消及超时状态保留原问题，重试由用户明确发起。全文采用本站关键词/中文词组段落检索，无新增检索服务依赖；只使用家庭公开已发布文章。取消会在下一段服务回复到达时生效，不能承诺撤销服务方已产生的用量。进程中断的请求在五分钟保护期后标记失败，不自动再次生成。
