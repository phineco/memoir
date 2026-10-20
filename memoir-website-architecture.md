# 家音网站架构

更新日期：2026-10-20。基于现有仓库重建，不代表已实现仓库之外的原设计。

## 一、产品与流程

外部 AI 助手整理长辈口述，输出初稿、金句、待核实事项和事件；管理员导入，家人阅读与纠正；修订经网页或同步包保存；管理员人工确认后发布分享快照。

账号负责登录、权限和作者身份；人物负责家族关系、讲述对象与讲述者，两者通过认领连接。人物采用单一挂靠上级、祖先路径和配偶关系，是家族树展示模型，尚非任意复杂亲缘关系图。

## 二、数据模型

28 张业务表，另有迁移工具维护的 `schema_migrations`。主键为应用生成的不透明字符串，保留审计与软删除字段。

| 分类 | 表 |
|---|---|
| 身份与家庭（5） | `users`、`families`、`family_members`、`invites`、`sms_codes` |
| 人物（2） | `persons`、`portraits` |
| 原始资料（2） | `source_files`、`transcripts` |
| 故事与关联（8） | `interviews`、`drafts`、`quotes`、`verification_items`、`person_links`、`new_persons`、`interview_persons`、`interview_viewers` |
| 事件与照片（2） | `timeline_events`、`photos` |
| 互动与分享（3） | `comments`、`likes`、`share_snapshots` |
| 同步（2） | `sync_log`、`person_id_map` |
| AI（3） | `ai_memories`、`ai_messages`、`ai_cache` |
| 计划（1） | `writing_plans` |

`Interview` 同时承载人工文章和访谈故事；`Draft` 保存正文版本。`PersonLink` 保存文字提及的对应，`InterviewPerson` 保存结构化人物关联。`SourceFile` / `Transcript` 有模型与样例，不代表已交付录音上传或自动 ASR。

建表 SQL 仅用于新 MySQL 库；已有库用 `migrate.py` 升级。`create_all` 创建缺失表，不会给已有表补列。

## 三、运行结构

| 文件 | 职责 |
|---|---|
| `app.py` / `config.py` | 应用初始化与环境配置 |
| `views.py` / `access.py` | 页面、API、家庭权限、故事可见性 |
| `models.py` | 数据模型与会话 |
| `sync_engine.py` | 入库、人物匹配、修订与幂等 |
| `ai.py` | AI 问答、摘录、记忆、导读、计划 |
| `storage.py` / `sms.py` | 磁盘与 OSS 存储、短信验证码 |
| `sanitize.py` | 富文本白名单清洗 |
| `templates/` / `static/` | Jinja 页面、样式、朗读脚本 |

本地为 SQLite + 磁盘，云端为 MySQL + OSS 私有桶，gunicorn 经 nginx 提供服务。`APP_ENV=cloud` 只改变默认照片存储后端，数据库须显式配置。

## 四、访问与发布边界

家庭资料要求有效成员资格；未知与无权访问家庭均返回 404。成员按故事可见性阅读、创作和互动；管理员维护人物、计划、导入和分享；创建者管理成员角色。旧创建者仅在从未有成员记录时兼容为 owner。

草稿仅作者可见；已发布故事按 `public/private/specific` 过滤。照片、AI 摘录、故事来源事件也遵守访问边界。已经签发的 OSS URL 在失效前仍可访问。

公开入口为欢迎页、登录/注册/找回、指南、邀请码与已发布分享页。分享是生成时的快照，修改故事不会自动更新旧快照，须重新生成或下线。

## 五、AI 与外部助手

网站内置 AI 使用兼容 chat completions 的接口，附带有限资料摘录、最近聊天与按家庭/用户保存的记忆，没有全文检索或向量库。事实仍需人工核实。

外部采访助手须另行配置，不随本仓库交付。目前通过管理员粘贴数据或带登录会话调用 API 对接，没有独立 MCP 服务或小程序。

## 六、尚未实现

微信 OAuth、完整录音转写与整理流水线、自动小传任务、异步队列、Docker 编排、全文检索、书籍排版与导出。预留字段不等于已交付能力。
