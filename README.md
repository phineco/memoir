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
| 周报 | `/f/<family_id>/weekly`；故事、金句、待核实和新人物；可生成 AI 导读 |
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

## 样式开发与测试

修改模板工具类或 `static/src.css` 后，在本地编译并提交 `static/tailwind.css`：

```bash
npm install --no-save --package-lock=false tailwindcss@3.4.17
./node_modules/.bin/tailwindcss -c tailwind.config.js -i static/src.css -o static/tailwind.css --minify
```

服务器只需 Python 依赖。测试使用独立数据库，不运行演示 seed，不调用真实 AI / 短信：

```bash
python -m pip install -r requirements-dev.txt
python -m pytest -q
```

## 资料导航

- [架构与能力边界](memoir-website-architecture.md)
- [sync-json 同步协议](memoir-sync-design.md)
- [部署、初始化与升级](DEPLOY.md)
- [项目约束](AGENTS.md) / [项目记忆](MEMORY.md)
