# 家音 · 回忆录网页原型 v0.1

技术栈：**Flask + Jinja2**（服务端渲染）+ SQLAlchemy（ORM）
表结构：`~/workspace/your_files/memoir-mysql-schema.sql`（MySQL 5.7），模型见 `models.py`（15 张表一一对应）

## 快速运行

```bash
cd ~/workspace/memoir-prototype
pip install -r requirements.txt
python seed.py        # 灌样本数据（王家：王德顺/王建军/王秀兰/李桂香）
python app.py         # 启动，打开 http://localhost:5000
```

## 页面

| 地址 | 说明 |
|---|---|
| `/` | 家庭列表 |
| `/f/wang` | 家族树（ECharts，点击节点进人物页） |
| `/f/wang/person/p02` | 人物页：小传 + 照片墙 + 按年时间轴 |
| `/f/wang/stories` | 故事列表 |
| `/f/wang/story/iv1` | 故事详情：初稿 + 金句 + 待核实 + 人物对应 |
| `/f/wang/weekly` | 本周周报页（固定框架读库） |
| `/api/weekly-report?family_id=wang&week=42` | 周报聚合接口（JSON） |
| `/s/wang-week1` | 分享页（token + 密码，样本密码 `jiayou123`） |
| `/login` `/register` | 登录/注册（原型：手机号+密码；正式版：微信+手机号） |
| `POST /f/wang/story/iv1/comment` | 发表评论/追评（需登录） |
| `POST /api/like` | 点赞/取消点赞（文章或评论） |
| `/f/wang/write` | 写文章（需登录）：Quill 富文本编辑器（字体/段落/列表/颜色）+ 🎤语音转文字（浏览器 Web Speech API，中文），可选讲述对象/关联人物/时间段；提交时选「保存草稿」或「发布」 |
| `/f/wang/drafts` | 我的草稿箱（需登录，仅看自己的草稿，可继续编辑、一键发布） |
| `POST /f/wang/story/<id>/publish` | 草稿发布（仅作者） |
| `/f/wang/story/<id>/edit` | 继续编辑草稿（仅作者；每次保存生成新版本，旧版本保留在 drafts 表） |
| `/f/wang/tree/add` | 添加人物（仅家庭管理员=创建者）：姓名/挂靠上级/关系/别名/性别/配偶/生卒年/排序 |
| `/f/wang/tree/<pid>/edit` | 编辑人物（仅管理员）：改资料、改挂靠（自动重算子孙 parent_ids、防环）、关联/解绑登录账号、设配偶（双向） |
| `POST /f/wang/tree/<pid>/delete` | 删除人物（仅管理员，软删除；名下有人时拒绝） |
| `POST /f/wang/tree/<pid>/claim` | 👤 这是我：登录用户把自己关联到树上人物（一人只关联一个），家族树节点显示 👤昵称 |
| `POST /f/wang/tree/<pid>/unlink` | 解除人物与账号的关联（管理员或本人） |
| `/f/wang` 成员管理 | 👥 成员管理（仅创建者可见）：成员列表、添加成员（设为管理员/普通成员）、移除成员；一个家庭可有多个管理员 |
| `/f/wang/person/<pid>/portrait/edit` | ✏️ 编辑人物小传（仅管理员）：小传由 skill 自动提炼，手动修订保存为新版本，历史版本保留 |
| `POST /f/wang/person/<pid>/photos/upload` | 📤 照片上传（登录用户）：拍照（手机调相机）或相册选择，描述必填，jpg/png/gif/webp≤10MB；存储后端按配置走本地或 OSS |
| `/guide` | 📖 使用指南：三步上手、家人/管理员功能、内容流程、常见问题（顶栏常驻入口） |
| `/f/wang/shares` | 🔗 分享管理（仅管理员）：从本周周报生成快照 → 预览 → 人工确认发布（随机 token + 访问密码）→ 下线/删除；未确认的快照对外 404 |
| `POST /f/wang/person/<pid>/photos/<photo_id>/delete` | 🗑️ 删除照片（上传者本人/管理员）：存储对象一并删除 |
| `POST /f/wang/story/<sid>/comments/<cid>/delete` | 🗑️ 删除评论（作者本人/管理员）：软删占位"该评论已删除"，子评论保留 |
| `/f/wang/sync` | 🔄 同步入库（仅管理员）：粘贴 skill 输出的 sync-json → 校验 → 入库；`POST /api/sync` 接口同逻辑（供 MCP/小程序） |
| `/f/wang/weekly/42/ai-summary` | ✨ 生成本周 AI 导读（管理员 POST，按周缓存；读 `ai_cache`） |
| `/f/wang/ask` | 🤖 问 AI（登录）：家庭知识库问答 + 用户记忆，需配置 `DEEPSEEK_API_KEY` |
| `/f/wang/plans` | 📋 写作计划（登录）：管理员定"先写谁"，可 AI 给建议再手动改；`GET /api/writing-plan` 供 skill 拉取 |
| `/register` | 📱 注册：手机号 + 短信验证码（阿里云 Dysmsapi V3 签名直调；未配置时开发模式直接显示验证码） |
| `/forgot-password` | 🔑 短信自助找回密码（创建者忘密码也不用找人） |
| `/join/<code>` | 📨 邀请链接：注册/登录后自动加入家庭 |
| `/families/new` | 🏠 创建家庭（登录用户）：填名称+可选代号，创建者自动成为 owner；首页列表登录后可见入口 |
| `POST /f/wang/members/create-account` | ➕ 为家人开通账号（管理员）：手机号或用户名 + 密码，老人可由子女代建；开通后自动加入家庭为成员，凭证仅展示一次 |
| `POST /f/wang/members/<mid>/reset-password` | 🔑 重置成员密码（创建者可重置所有人，管理员只能重置普通成员；新密码≥6位，仅展示一次） |

**安全**：写文章/改草稿的富文本经 `sanitize.py` 白名单清洗（bleach）防 XSS；照片上传加文件头魔数校验。

**AI（DeepSeek，预置提示词直调）**：`ai.py`；配置项见 `.env.example`（`DEEPSEEK_API_KEY`/`DEEPSEEK_BASE_URL`/`DEEPSEEK_MODEL`，不填则 AI 功能优雅降级）；所有调用按官方 rate_limit 文档透传 `user_id`（本站不透明内部 id）做内容安全/KVCache/调度三层隔离，429 返回"AI 繁忙请稍后再试"；🤖 问 AI（`/f/<fid>/ask`）：system prompt 含项目架构/目的/功能说明 + 家庭知识库（人物/故事/金句/待核实/待定新人物）+ 用户记忆，回答须注明来源、绝不虚构，并引导补充缺失、做采访规划；用户记忆存 `ai_memories`（每用户 profile 一条，对话后自动提炼更新）；聊天记录 `ai_messages`；周报 AI 导读按周缓存 `ai_cache`（`weekly:<fid>:<week>`），管理员一键生成。

**skill 同步**：6 种 sync-json 数据包（tree_upsert / interview_upsert / verification_update / new_person / person_status / revision_sync）入库引擎见 `sync_engine.py`；人物按映射表→姓名→别名对应，对不上不硬挂；`client_id` 幂等；同步日志 `sync_log`，周报 `unsynced_count` 为本周失败条数。

**语音朗读**：故事/人物小传/周报三处共用 `static/read-aloud.js`（浏览器 speechSynthesis，慢速/正常两档，逐段高亮，可随时停止；iOS 需点击触发）。

## 环境配置（本地部署 / 云环境开关）

```bash
# 本地部署（默认）：SQLite + 本地磁盘存照片
python app.py

# 云环境：MySQL + 阿里云 OSS 私有桶
export APP_ENV=cloud
export DATABASE_URL=mysql+pymysql://user:pass@host:3306/memoir?charset=utf8mb4
export OSS_REGION=cn-hangzhou OSS_BUCKET=xxx \
       OSS_ACCESS_KEY_ID=xxx OSS_ACCESS_KEY_SECRET=xxx
python app.py
```

配置项见 `.env.example`。`APP_ENV=local|cloud` 一键切换环境；`STORAGE_BACKEND=local|oss` 可单独覆盖存储后端（默认跟随 `APP_ENV`）。OSS 用 Python SDK v2：私有桶 `put_object` 上传、照片展示走带过期时间的签名 URL（`OSS_URL_EXPIRES`，默认 3600 秒）；缺配置时上传会给出明确提示。依赖新增 `alibabacloud-oss-v2`。
| `/f/wang/person/<pid>/timeline/add` | ➕ 添加时间轴事件（仅管理员）：标题/日期/精度/描述，日期空则归入"待定时间" |
| `/f/wang/person/<pid>/timeline/<eid>/edit` | ✏️ 编辑时间轴事件（仅管理员） |
| `POST /f/wang/person/<pid>/timeline/<eid>/delete` | 🗑️ 删除时间轴事件（仅管理员，软删除） |
| 故事页 | 显示 🎙️讲述者（链接到人物页）；周报 API stories 含 `narrator` 字段 |
| 家族树节点 | 默认显示人名、出生/去世年份、别名、👤关联账号；登录且已认领人物时自动显示"对你：X"称谓（按辈分+性别+父系/母系+长幼计算，缺信息时降级为中性词） |
| 人物页 | 登录且已认领时显示"🧭 与你的关系：X" |

**互动功能**：文章页显示观看数、点赞数；登录用户可在文后评论、对评论追评（树形嵌套）；点赞可取消。草稿仅作者可见（详情页 404、列表/周报不收录），发布后全家人可见。演示账号：`13800000000` / `demo123`（含一篇示例草稿《奶奶的针线活》）。

## 部署

见 [DEPLOY.md](./DEPLOY.md)：本地部署 5 分钟跑起来；云部署（ECS + MySQL 5.7 + OSS + nginx + HTTPS）一步步照做。生产初始化用 `python create_admin.py`（`seed.py` 会清空表，仅演示用）。

## 切 MySQL 5.7

```bash
export DATABASE_URL="mysql+pymysql://user:pass@host:3306/memoir?charset=utf8mb4"
python seed.py && python app.py
```

先用 `memoir-mysql-schema.sql` 建库，再灌数据。SQLite 仅用于本地演示。

## 部署（后期）

`docker-compose.yml`（待加）：mysql:5.7 + api（gunicorn/uvicorn→Flask 用 gunicorn）+ nginx。
AI 在线处理：RQ/Celery 异步队列跑整理任务，前端轮询 `/api/interviews/<id>` 状态。
