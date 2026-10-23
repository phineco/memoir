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
- 短信：`ALIYUN_SMS_ACCESS_KEY_ID/ACCESS_KEY_SECRET/SIGN_NAME/TEMPLATE_CODE`；公网必须配好；缺配置时停用短信验证，不能降级返回开发验证码。
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

业务表共 43 张，`schema_migrations` 由迁移程序维护。已有库不能重新导入建表 SQL。`create_admin.py` 交互输入密码，不清空已有记录；**生产不得执行 `seed.py`**。`install.sh` 只建立项目虚拟环境、安装依赖和缺省配置，不再自动执行 seed 或修改数据库。

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
ExecStartPre=/opt/memoir/.venv/bin/python tools/check_database.py
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
.venv/bin/python tools/check_database.py
sudo systemctl start memoir
```

`--dry-run` 只读预演，不建数据库或迁移记录表。周报当前年周按 `APP_TIMEZONE`（默认 Asia/Shanghai），服务 `TZ` 须与之相同；旧无时区时间需核对后再调整。

`tools/check_database.py` 是只读检查，使用与网站相同的 `.env`/环境变量，核对当前连接可见的模型表、列与迁移记录；成功退出 0，结构/迁移尚未就绪退出 1，配置/连接检查失败退出 2。不会创建 SQLite 文件或迁移记录，不修改已有库，不输出连接串、密码或业务资料。只按网站同一服务账号、虚拟环境、工作目录及环境执行；面板注入的环境变量优先于 `.env`，只在另一个终端检查不能证明网站连接一致。任一步失败都不要继续启动。宝塔可将此命令放在启动前检查；systemd 示例已加入 `ExecStartPre`，应用 worker 自身仍不建表。此检查不检查索引、约束、全部读写权限或备份恢复，不代替完整上线验收。

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
- 故事页在 `onboarding.touch` 报 `ProgrammingError`：先运行只读检查，重点核对 `010_family_visits.sql` 的表/列及其他未执行迁移。只凭异常类型无法断言漏迁移：新日志的 `database_error_code=1146/1054` 表示表/列不匹配，`1142` 等须核对数据库账号权限，`1064` 须核对 SQL 和数据库兼容性。缺表/列时网页返回 503 及升级提示，不自动建表或绕过家庭权限。若迁移记录显示完成而检查仍缺表/列，先核对相同数据库及实际结构；不要删除迁移记录、删表重建或运行初始化强行“修复”。
- 生产日志 `version=development`：部署缺少 Git/`RELEASE.json` 且未配置 `APP_VERSION` 时无法识别发布版本，不代表服务器在开发模式。优先使用含版本清单的发布包，或将 `APP_VERSION` 配为实际部署提交/发布号后重启；它不能代替数据库迁移。

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

## 2026-10-23 短信生产保护

短信参数不完整时，发送与校验都停用，不返回或记录验证码。仅 `APP_ENV=local` 且显式设置 `SMS_DEVELOPMENT_MODE=1` 才可显示本地测试码；默认值为 0，cloud 环境始终禁止开发码。接入真实短信后不能使用此前的开发码，升级前签发的旧无来源标记验证码也失效，须重新获取。无需表结构迁移。

## 版本、故障编号与耗时

每个响应提供 `X-Request-ID`、`X-App-Version` 和 `Server-Timing`；版本优先取 `APP_VERSION`，其次发布包 RELEASE.json，再回退 Git，故不要求生产有 .git。未预期异常页/JSON 提供故障编号，流式 AI 中途失败同样带编号。日志仅记录端点、状态、异常类型和代码位置，不记录请求参数、正文、验证码或异常中的 SQL 参数。将 Gunicorn error log 收集到受限位置；启动、代理和迁移错误须通过版本及对应进程日志核查。

`REQUEST_LOGGING=1` 开启安全的请求耗时记录。应用/SQL 耗时为响应开始前的服务器测量，SQL 已包含在应用耗时中；不能当作网络、静态资源、完整 AI 流或手机首屏耗时。生产的日志留存、告警接收和抽样频率由运维确认。

## AI 记忆重置（008）

上线前停服、备份并执行迁移 008，新增每账号/家庭的重置边界；旧摘要继续按原资料范围兼容，首次重置会清空本人全部版本摘要并取消旧生成。旧对话仍留存但不进入新请求或当前展示，第三方及备份处理需单独申请。MySQL 写入记忆和问答时锁定重置边界，防止旧生成覆盖重置。此版本隐私政策为 2026-10-23.1，首次人工反馈按 Louis 指定的 3 个工作日执行，不等同于完成删除。

## 故事检索（009）

上线前停服并执行 009。迁移为历史正文建立可读文字列，保留原 HTML 和历史版本，不因标签属性产生搜索命中；首次回填按 200 条分批。迁移中断后可重跑，已存在列会跳过并继续补齐未回填记录。新建/修订和同步导入的正文在同一事务更新搜索文字；搜索只用当前有效版本和未放弃金句，先做家庭与可见性过滤再计数分页。无需新服务。

## 上手引导与首次观察（010）

先执行 010。引导与首次访问/阅读/正式保存状态按账号加家庭记录，不记录正文或阅读的文章 ID；完成状态从实际角色和资料计算，认领不是写作前提。可跳过或从帮助重新打开；既往作者不纳入新增首篇转化分母，不把首次观测时间伪称历史首次访问。新动作与正式保存同一事务记录。

## 隐私申请运营交接（011）

先执行 011。个人中心提供本人申请、补充、撤回与处理记录；只有 `OPERATIONS_USER_IDS` 中明确配置的有效站点账号能进入 `/operations/privacy`，不根据家庭管理员角色推定权限。由有权限的运维核对既有账号内部 ID 后配置并重启，禁止把测试账号 ID 用到生产。

未配置有效运营账号时，站内不接收新申请，页面明确引导联系邮箱，避免无人处理的申请被误认为受理。启用前由 info@scyllatech.cn 对应运营人员确认每日查阅队列，3 个工作日内首次人工反馈；这不是删除完成期限。队列优先展示待首次反馈的较早申请。

运营反馈须说明核验/处理情况；标记完成前必须明确确认已核验身份并已实际处理。系统只记录进度，不自动注销、删除家庭资料、备份或外部服务记录。多方共享资料分别核验范围。补充、反馈和撤回有版本控制，保留有序处理记录；不要把密码或短信验证码作为核验材料。真实受理 SLA、人员值守及删除流程仍需运营执行证据。

## 运营周度指标（012）

先在恢复副本验证迁移，再停服、备份、单进程执行 001–012 中未执行的迁移后启动。012 增加状态样本、独立首次发布证据与人工核验表、AI 重试关联字段及核实解决时间；历史只回填明确的首次发布时间，不猜测旧逻辑问题或核实解决时间。当前隐私政策版本为 `2026-10-23.4`，不为旧账号补记同意。

`OPERATIONS_USER_IDS` 有效账号可从个人中心进入指标页；家庭管理员默认无此权限。`USAGE_METRICS_ENABLED=0` 默认关闭浏览器保留/恢复状态采集；开启前确认告知、处理依据、有效运营账号与清理安排。每日以服务账号执行 `.venv/bin/python tools/usage_retention.py --apply` 清理 90 天前状态样本；省略参数先预览，不输出个体明细。此工具不操作故事或备份，清理会使旧周的浏览器样本不完整。此次没有安装定时任务。详细口径、人工证据要求见 [METRICS.md](METRICS.md)。

本轮迁移 008–012 涉及结构及数据回填，不能按纯静态 UI 版本直接切回旧代码。恢复方案须同时核对迁移后的资料、停写与备份，禁止通过删新表回滚。

## 家人声音 v1（013，默认关闭）

详细边界与供应商核验见 [P2_11_VOICE_2026-10-23.md](P2_11_VOICE_2026-10-23.md)。已有部署先在恢复副本验证，再停 web 与声音后台进程、备份、单进程执行 001–013 中未执行的迁移。013 增加 5 张声音表和正文版本授权字段，不补造同意记录。当前协议版本 `2026-10-23.2`，隐私政策 `2026-10-23.5`；声音另有单独同意版本，旧注册确认不能替代。

默认 `VOICE_ENABLED=0`、`VOICE_COMPLIANCE_APPROVED=0`、`VOICE_DECEASED_ENABLED=0`，所有家庭名额和字符预算均为 0。当前只交付代码与模拟验证；未安装服务、未设置真实 Key、未提交个人录音。未开启时普通朗读继续使用浏览器。个人中心的本人声音授权撤回及后台清理不随总开关消失。

真实开通前须完成服务商 API 场景许可、实名/授权材料、敏感信息必要性与影响评估、保存/删除安排及真实验收；模型广场体验许可不能替代正式 API 场景许可，已故者另行确认。使用至少 32 字符的随机 `SECRET_KEY`；弱会话密钥时声音请求和真实后台调用拒绝执行。仅在服务器安全配置中提供 `DASHSCOPE_API_KEY` 与北京 `VOICE_WORKSPACE_ID`，不读本机钥匙串、不复用视频默认音色。每个音色保留创建时业务空间与模型绑定；更换业务空间前必须处理旧空间音色，不能将旧删除任务发往新空间。

安装受维护的 FFmpeg，验证服务账号能执行，按需配置 `VOICE_FFMPEG` 绝对路径；记录实际版本并更新安全补丁。配置有效 `OPERATIONS_USER_IDS`，通过受限材料核验后再在界面确认授权。只有单独同意与运营核验完成才开放采样。

将 `VOICE_FAMILY_LIMITS` 设置为显式家庭额度，例如 `.env` 中使用 `VOICE_FAMILY_LIMITS='{"实际家庭内部ID":{"voices":2,"monthly_characters":100000}}'`。这是内部开通及保守预算，不是支付、套餐或供应商结算账单；未配置家庭不能新建音色或发起新的合成，已有缓存不重复预留。字符额度包含失败和未知请求，避免不明费用被反复释放后重试。

网页进程不执行云端长任务。可先以服务账号执行一次 `.venv/bin/python -B tools/voice_jobs.py --limit 10` 处理有限步骤；开通持续服务时复制并按实际路径修改 `tools/systemd/memoir-voice.service`，使用同一虚拟环境、配置、时区及私有媒体存储，以 `--watch` 每两秒检查队列。示例未安装；宝塔可用独立守护进程实现同一命令，不能把队列任务放进每个 Gunicorn worker。退出信号会等待当前步骤结束，更新前等待后台退出后再迁移。

`VOICE_ENABLED=0` 停止新的合成/播放；后台仍可处理已撤回资料。`VOICE_COMPLIANCE_APPROVED=0` 阻止新云端生成，已有资料删除仍使用有效凭据。超时或租约失效不表示供应商没有受理，系统不自动重复复刻/付费合成；运营先停止原后台任务，核对前缀资源和计费，留证后继续删除。不能仅清空数据库状态重做。站点运营可通过 `/operations/voices` 处理，家庭管理员不能访问该页面。

本地样本与音频位于 `UPLOAD_DIR/voice/` 的私有子目录，文件 0600、目录 0700；nginx 禁止将媒体根目录公开映射。OSS 必须使用私有桶，音频由本站鉴权回传，不下发 OSS 签名地址。多实例须共用安全媒体与同一数据库。备份导出须包含声音对象，备份校验将检测样本/音频引用是否缺失；备份保留及第三方临时结果另有处理安排。

恢复旧数据库/媒体前，先关声音和生成开关，停后台并对照备份外保存的撤回/删除处理记录，清理已撤回声音及旧模型引用，禁止恢复后自动生成或重新启用。不能以旧备份恢复音色代替重新授权。删除成功仅表示当前服务商模型确认不可用、本站样本和生成音频已清理；必要审计记录、已传至终端的内容及备份范围须分别说明。

## 首篇写作优化与可读文章导出（2026-10-23）

本次无新增数据库迁移、依赖或后台任务；此前未执行的 001–013 仍须按各自交接落实。发布时同时更新 Python、模板与已构建的 `static/dist/`，重启 web 进程；新增问题卡脚本包含在 15 项静态资源清单中，生产不需要 Node。完整范围与验证见 [实施记录](BATCH1_ARTICLE_EXPORT_2026-10-23.md)。

个人中心增加 `/account/exports`，家庭管理资料工具可打开 `/f/<family_id>/exports/articles?scope=family`。导出通过本站登录会话及 CSRF 验证，必须由应用处理，不配置 nginx 公共下载目录、静态别名或代理缓存。ZIP 在内存即时生成，发送前结束原读取事务并重查最新成员资格、文章范围和正文；没有持久导出包及清理任务。不改变 OSS 或照片、声音配置，也不把运维数据库备份交给用户。

单包上限 1000 篇、单篇正文 2 MiB、正文资料合计 8 MiB；可每批 100 篇下载。范围、篇数、当前版本、导出时间及文件校验值随包保存，照片、录音、小传、金句、评论、核实与历史版本未包含。超过限制、正文缺失或多个当前版本会明确失败，不能绕过校验生成“完整”包。此限制不保证任意规模家庭一次下载，后续媒体归档另做私有后台任务。

当前隐私政策版本更新为 `2026-10-23.6`，说明导出范围与已下载副本无法远程撤回；不为已有账号补造确认。部署后核查普通成员无法进入家庭导出、被移除成员无法下载、私密/指定人文章不混入家庭包，再用非真实个人资料验证下载解压及离线阅读。声音功能及真实生成继续默认关闭；本次没有生产发布或手机实机验收。

## 个人中心导航修复（2026-10-23）

从当前家庭进入个人中心，再打开“我的声音授权”或“我的家庭”时，保留经过成员权限验证的来源家庭导航；返回个人中心、打开家庭选择页或选择另一个家庭后，菜单使用对应家庭。品牌入口和“更多 → 切换家庭”也延续来源上下文，显式选择家庭时不自动跳回旧家庭。

本人声音授权仍可不带家庭参数独立访问，退出家庭或关闭声音功能不影响本人撤回。撤回后只保留仍有效的导航上下文，不恢复已退出家庭的资料访问。无权或已失效的显式家庭参数在读取时返回 404。

本次更新 Python 和模板，重启 web 进程生效；固定静态产物检查通过且内容无需变化。不新增数据库迁移，但此前未完成的 001–013 仍须先按升级流程补齐。隔离验证：283 项后端通过、5 项真实 MySQL 待独立服务；新入口/返回/切换家庭流程在 320/390/1280 三档大字浏览器通过，原 290 组布局及 13 个语音模拟通过。未推送部署，未冒充手机实机验证。

## 个人中心声音采集入口（2026-10-23）

“我的声音授权”新增本人选择、建立档案、单独同意、核验进度以及核验后的上传/现场录音、试听选段和提交复刻；与人物页共用声音表单及同一后台处理流程，提交后留在个人中心。仅列当前有效家庭中已关联本人的非已故人物，多个家庭时明确选择，未核实状态时不允许开始。个人入口不替其他人授权，不改变已故场景的默认关闭与专门流程；退家后的本人授权撤回仍可独立访问。

尚未开通、没有音色名额、未关联人物、待同意或核验、处理中、已有音色及删除中的原因分别提示。核验前不显示可用的文件输入或录音控件；不能通过修改请求参数绕过服务器校验。采样仍只保留选定的 10–60 秒片段，不成为完整录音档案，不提供任意文字合成。

不新增迁移或依赖；仍须按前文完成旧迁移及服务配置。原 `VOICE_ENABLED`、`VOICE_COMPLIANCE_APPROVED` 和家庭额度默认不变，界面新增不代表服务已开通。真实启用前核对服务商许可、单独同意、人工核验、家庭额度、后台任务及私有媒体；使用服务器实际可执行的 `VOICE_FFMPEG` 路径，并核对服务账号权限。此轮未提供密钥、未启动收费请求、未安装后台或修改生产配置。

验证：287 项后端通过、5 项原生 MySQL 待独立服务；隔离浏览器跑通个人入口授权/审核、录音启动取消及停止、录音上传、模拟克隆、版本缓存、合成标注、降级、删除与三档大字布局；个人中心导航专项、原 290 组页面布局和 13 个语音模拟通过。真实音质、许可、费用、手机麦克风及服务商删除仍须实际环境联调。
