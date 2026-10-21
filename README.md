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
python create_admin.py --phone 13800000000 --nickname 主持人 --family-name 我的家
python app.py
```

打开 `http://localhost:5000`。`python app.py` 开启调试模式，仅用于开发；生产使用 gunicorn，见 [部署说明](DEPLOY.md)。

如需样例，**仅在独立、可丢弃的演示数据库中**执行 `python seed.py`；它会清空多张业务表。样例家庭代号 `wang`，账号 `13800000000` / `demo123`。不要在已有数据或生产库运行。

## 已实现功能

| 模块 | 入口与说明 |
|---|---|
| 家庭 | `/` 仅列自己所属家庭；`/families/new` 创建；`/join/<code>` 邀请加入 |
| 家族树 | `/f/<family_id>`；人物增改、配偶、认领、相对亲属称谓 |
| 人物 | `/f/<family_id>/person/<person_id>`；小传、照片、时间轴、关联故事 |
| 故事 | `/f/<family_id>/stories`；阅读、朗读、评论与追评、点赞 |
| 创作 | `/f/<family_id>/write`、`/f/<family_id>/drafts`；富文本、浏览器语音输入、草稿、可见性 |
| 周报 | `/f/<family_id>/weekly`、`/f/<family_id>/weekly/<year>/<week>`；故事、金句、待核实和新人物；可生成 AI 导读 |
| 分享 | `/f/<family_id>/shares`；管理员确认后凭 `/s/<token>` 和密码访问快照 |
| 写作计划 | `/f/<family_id>/plans`；管理员定计划，可使用 AI 建议 |
| AI 问答 | `/f/<family_id>/ask`；流式回答、聊天记录和用户记忆 |
| 同步 | `/f/<family_id>/sync`、`POST /api/sync`；七类数据包，详见[同步协议](memoir-sync-design.md) |
| 使用指南 | `/guide` |

小传目前由管理员录入或修订并保留版本，仓库内没有自动生成小传的完整任务流程。朗读使用浏览器 `speechSynthesis`，语音输入使用 Web Speech API，可用性取决于设备、浏览器与授权。

## 权限与隐私

- 家庭页面和 API 均须登录且属于该家庭。角色为创建者 `owner`、管理员 `admin`、成员 `member`。
- `public` 表示**家庭内可见**；`private` 仅作者；`specific` 为作者及指定成员；草稿仅作者。
- 移除成员后撤销访问，管理员也不能跨家庭。添加已有成员使用精确账号或邀请码，不展示全站账号名单。
- 本地照片校验家庭资格；OSS 私有桶使用短期签名 URL，已签发 URL 在到期前仍可使用。
- AI 摘录、金句、待核实事项及故事来源事件按故事权限过滤。对外只提供人工发布的分享快照。

## 技术与配置

Flask + Jinja2、SQLAlchemy、Tailwind CSS 3；家族树 ECharts、编辑器 Quill。现有 **28 张业务表**，见[模型](models.py)和[建表 SQL](memoir-mysql-schema.sql)。`schema_migrations` 为迁移记录表，不计入业务表。

| 配置 | 含义 |
|---|---|
| `DATABASE_URL` | 默认 `sqlite:///memoir.db`；云端须显式配置 MySQL |
| `APP_ENV` | `local` / `cloud`；影响默认存储后端，不会自动配置 MySQL |
| `STORAGE_BACKEND` | `local` / `oss`，可覆盖环境默认值 |
| `SECRET_KEY` | 会话签名密钥，生产必须设置随机长值 |
| `UPLOAD_DIR` | 默认仓库内 `uploads/` |
| `OSS_*` | 私有桶、地域、凭据与签名有效期，见[环境示例](.env.example) |
| `DEEPSEEK_*` | AI 接口配置；缺少 key 时禁用；模型名按供应商实际可用配置核对 |
| `ALIYUN_SMS_*` | 阿里云短信；未配置时返回开发验证码，不能直接用于公网服务 |

`.env` 自动加载，不提交 Git。ECharts / Quill 仍从 CDN 加载，Tailwind 编译产物已自托管。

AI 采用资料摘录拼接提示词，并非全文检索：家庭知识默认上限约 6,000 字符，每篇故事摘录约 200 字符。资料多时可能无法覆盖所有故事；提示词要求“不虚构”不能替代家人核实。向供应商传递内部 `user_id` 也不能替代本站权限控制。

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

点击顶部用户名称进入个人中心，调整显示设置或查看本人在有效家庭中的草稿；帮助页会保留当前家庭的顶部导航。

人物的出生、去世分别支持公历与农历年/月/日，两套可独立选填；支持农历闰月及不完整日期，不自动换算。人物页、家人列表和 AI 参考资料会显示已录入的信息。旧年份按原历法迁入新增字段，未记载的月日保持为空。

**已有数据库更新此版本前须执行 `002_person_dual_calendar_dates.sql` 增量迁移**，具体顺序见 [部署文档](DEPLOY.md) 的双历日期升级说明；不能仅替换代码后直接启动。

## 邀请链接与二维码

家庭管理中的有效邀请同时提供公开链接和可下载的 PNG 二维码。公开域名由 `PUBLIC_BASE_URL` 配置，默认 `https://family.scyllatech.cn`，避免反向代理生成内网地址。二维码在本站生成，预览和下载不消耗邀请次数；旧邀请码仍可使用原来的有效期和次数。

## 资料导航

- [架构与能力边界](memoir-website-architecture.md)
- [sync-json 同步协议](memoir-sync-design.md)
- [部署、初始化与升级](DEPLOY.md)
- [备份、验证与隔离恢复](BACKUP.md)
- [项目约束](AGENTS.md) / [项目记忆](MEMORY.md)
