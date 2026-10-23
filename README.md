# 家音 · 家庭口述回忆录

家音帮助家庭把长辈口述整理成故事，通过全家阅读、补充和核实，逐步积累人物小传、照片与人生时间轴。

当前是 Flask 服务端渲染原型。网站负责存储、协作、展示和分享；采访整理主要由外部 AI 助手完成，经 `sync-json` 导入。录音自动转写流水线、微信 OAuth、异步整理队列、Docker 编排和排版成书尚未实现。

## 本地运行

要求 Python 3.10+，推荐 3.12。从仓库根目录执行：

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
cp .env.example .env
# 在 .env 配置随机 SECRET_KEY；默认 SQLite + 本地照片目录。
python init_db.py
python migrate.py
python create_admin.py --phone 13800000000 --nickname 主持人 --family-name 我的家
python app.py
```

打开 `http://localhost:5000`。`python app.py` 开启调试模式，仅用于开发；生产使用 gunicorn，见 [部署说明](DEPLOY.md)。

应用启动只初始化连接池，不建表或修改结构。`init_db.py` 只允许空库，已有表会拒绝；已有库更新时备份、停止服务后单独执行 `python migrate.py`，成功后再启动。初始化和迁移都只运行一个进程。

如需样例，**仅在独立、可丢弃的演示数据库中**执行 `python seed.py`；它会清空多张业务表。样例家庭代号 `wang`，账号 `13800000000` / `demo123`。不要在已有数据或生产库运行。

## 已实现功能

| 模块 | 入口与说明 |
|---|---|
| 家庭 | `/` 仅列自己所属家庭；`/families/new` 创建；`/join/<code>` 邀请加入 |
| 家族树 | `/f/<family_id>`；人物增改、配偶、认领、相对亲属称谓 |
| 人物 | `/f/<family_id>/person/<person_id>`；小传、照片、时间轴、关联故事 |
| 故事 | `/f/<family_id>/stories`；阅读、朗读、评论与追评、点赞、家人核实建议与作者版本修订 |
| 创作 | `/f/<family_id>/write`、`/f/<family_id>/drafts`；富文本、浏览器语音输入、草稿、本机自动恢复、可见性 |
| 周报 | `/f/<family_id>/weekly`、`/f/<family_id>/weekly/<year>/<week>`；故事、金句、待核实和新人物；可生成 AI 导读 |
| 分享 | `/f/<family_id>/shares`；管理员确认后凭 `/s/<token>` 和密码访问快照 |
| 写作计划 | `/f/<family_id>/plans`；管理员定计划，可使用 AI 建议 |
| AI 问答 | `/f/<family_id>/ask`；流式回答、全文段落依据、问题恢复、显式重试/取消、请求去重 |
| 同步 | `/f/<family_id>/sync`、`POST /api/sync`；七类数据包，详见[同步协议](memoir-sync-design.md) |
| 使用指南 | `/guide` |

小传目前由管理员录入或修订并保留版本，仓库内没有自动生成小传的完整任务流程。朗读使用浏览器 `speechSynthesis`，语音输入使用 Web Speech API，可用性取决于设备、浏览器识别服务与麦克风授权；服务不可用时可改用手机键盘听写。两处语音共用启停、取消和超时释放流程，已输入文字不被替换，不接入额外云转写。

## 权限与隐私

用户服务协议 `/terms` 和隐私政策 `/privacy` 可匿名查看；注册、登录、个人中心与页脚均提供入口。自行注册须明确勾选当前版本，在发送注册短信和创建账号前校验，并保存协议版本与 UTC 确认时间；不会自动补记已有用户或代开账号的同意。公开权利申请邮箱默认为 `info@scyllatech.cn`，可通过 `PRIVACY_CONTACT_EMAIL` 配置。已有库上线前执行迁移 003，具体见 [部署说明](DEPLOY.md#协议与隐私政策)。

- 家庭页面和 API 均须登录且属于该家庭。角色为创建者 `owner`、管理员 `admin`、成员 `member`。
- `public` 表示**家庭内可见**；`private` 仅作者；`specific` 为作者及指定成员；草稿仅作者。
- 移除成员后撤销访问，管理员也不能跨家庭。添加已有成员使用精确账号或邀请码，不展示全站账号名单。
- 本地照片校验家庭资格；OSS 私有桶使用短期签名 URL，已签发 URL 在到期前仍可使用。
- AI、周报和分享仅使用已发布且家庭内公开的故事，不自动使用私密或指定人文章。AI 旧对话、记忆与缓存须匹配当前公开资料版本才复用；故事来源事件继续按阅读权限过滤。

## 技术与配置

Flask + Jinja2、SQLAlchemy、Tailwind CSS 3；家族树 ECharts、编辑器 Quill。现有 **43 张业务表**，见[模型](models.py)和[建表 SQL](memoir-mysql-schema.sql)。`schema_migrations` 为迁移记录表，不计入业务表。

| 配置 | 含义 |
|---|---|
| `DATABASE_URL` | 默认 `sqlite:///memoir.db`；云端须显式配置 MySQL |
| `DB_POOL_RECYCLE_SECONDS` | MySQL 连接最长复用秒数，默认 1800；取用连接前始终校验存活，详见部署说明 |
| `APP_ENV` | `local` / `cloud`；影响默认存储后端，不会自动配置 MySQL |
| `STORAGE_BACKEND` | `local` / `oss`，可覆盖环境默认值 |
| `SECRET_KEY` | 会话签名密钥，生产必须设置随机长值 |
| `UPLOAD_DIR` | 默认仓库内 `uploads/` |
| `OSS_*` | 私有桶、地域、凭据与签名有效期，见[环境示例](.env.example) |
| `DEEPSEEK_*` | AI 接口配置；缺少 key 时禁用；模型名按供应商实际可用配置核对 |
| `ALIYUN_SMS_*` | 阿里云短信；缺配置时停用，显式本地测试模式除外 |

`.env` 自动加载，不提交 Git。ECharts、Quill 与 Tailwind 编译产物均自托管，不要求生产环境访问 CDN。

AI 问答在家庭公开故事全文中进行词组匹配，选取最多六段相关内容，页面显示检索原文和可点击来源；不是语义向量检索，也不保证覆盖所有相关事实。计划建议等资料摘要仍有长度边界。提示词不能替代家人核实，内部 `user_id` 不能替代本站权限控制。失败保留原问题，同一请求编号不重复调用模型；取消会在上游下一段回复到达时停止，不能撤销已产生用量。

## 长期保存与周报时间

周报按 **ISO 年 + 周数** 区分，API 使用 `year`、`week`，返回值包含年份；省略年份或打开旧链接时取当前 ISO 年。年末某些日期属于下一 ISO 年，并非按公历年份直接截取。导读缓存使用 `weekly:<family_id>:<year>:<week>`；旧无年份缓存保留供核查，但不自动复用，请重新生成。

`APP_TIMEZONE` 默认 `Asia/Shanghai`，用于判断当前年周。历史审计时间是无时区本地时间，服务进程 `TZ` 应与该设置一致；已有数据若原先使用其他时区，先核对时间含义再安排迁移，不能自动猜测转换。

备份与隔离恢复命令见 [BACKUP.md](BACKUP.md)。归档包含数据库及本地媒体；OSS 必须先导出对象。恢复只写入空目标，不能覆盖现有数据库或照片目录。

## 样式开发与测试

保留 Tailwind 3.4.17，布局、按钮和主题由 `static/ui.css` 统一维护。前端构建工具及第三方文件的固定版本与 SHA-256 见 `tools/frontend.lock.json`；UI 测试依赖锁在 `package-lock.json`。服务器使用已提交的 `static/dist/`，无需 Node 或 CDN。

```bash
python tools/frontend.py bootstrap
python tools/frontend.py build
python tools/frontend.py check
npm ci --ignore-scripts
npx playwright install chromium
UI_BROWSER_CHANNEL=chromium python tools/run_ui.py
```

修改模板工具类、样式、脚本或固定版本依赖后，重建并提交 `static/dist/`。`bootstrap` 仅开发/CI 需要联网；已具备对应版本的独立工具时可指定 `TAILWIND_BIN`，执行前仍核对官方校验值。UI 测试始终使用临时 SQLite 与上传目录，并屏蔽第三方资源请求。

显示设置支持本地字体、18/22/26 正文字号、清新/暖纸/高对比主题与简洁模式，仅保存在当前浏览器，不修改其他家人的习惯。构建及版本发布见 [部署文档](DEPLOY.md)。

服务器只需 Python 依赖。测试使用独立数据库，不运行演示 seed，不调用真实 AI / 短信。GitHub Actions 提供 Python 3.10 / 3.12 回归及 MySQL 5.7 迁移、原生备份恢复验证：

```bash
python -m pip install -r requirements-dev.txt
python -m pytest -q
```

## 个人中心与人物日期

手机先点固定顶栏“菜单”展开导航；点击用户名称进入个人中心，调整显示设置或查看本人在有效家庭中的草稿。帮助页会保留当前家庭的顶部导航。

人物的出生、去世分别支持公历与农历年/月/日，两套可独立选填；支持农历闰月及不完整日期，不自动换算。人物页、家人列表和 AI 参考资料会显示已录入的信息。旧年份按原历法迁入新增字段，未记载的月日保持为空。

**已有数据库更新前须停服、备份并执行 `python migrate.py`，按序完成 001–013 的未执行迁移（含 AI 重置、正文检索、首次引导、隐私申请、指标及家人声音）**，具体顺序见 [部署文档](DEPLOY.md)；不能仅替换代码后直接启动。

## 邀请链接与二维码

家庭管理中的有效邀请同时提供公开链接和可下载的 PNG 二维码。公开域名由 `PUBLIC_BASE_URL` 配置，默认 `https://family.scyllatech.cn`，避免反向代理生成内网地址。二维码在本站生成，预览和下载不消耗邀请次数；旧邀请码仍可使用原来的有效期和次数。

## 资料导航

- [架构与能力边界](memoir-website-architecture.md)
- [sync-json 同步协议](memoir-sync-design.md)
- [部署、初始化与升级](DEPLOY.md)
- [备份、验证与隔离恢复](BACKUP.md)
- [项目约束](AGENTS.md) / [项目记忆](MEMORY.md)

## 2026-10-22 优先级修复

P0/P1 八项修改与验证记录见 [实施说明](PRIORITY_FIXES_2026-10-22.md)。已有库先备份并迁移，再启动新版。正文恢复仅在当前浏览器，各窗口独立保留；管理员密码结果只在服务器短期保存。故事修订保留历史版本，旧窗口不能覆盖新版本；周报及故事列表按首次发布时间，旧资料明确标注推定。电子书继续仅展示功能预告。
