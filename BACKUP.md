# 备份与恢复演练

`backup.py` 归档数据库、媒体文件与 SHA-256 清单，支持 SQLite / MySQL 原生备份。恢复只允许全新 SQLite 文件或空 MySQL 库、全新媒体目录，没有覆盖生产数据的强制选项。

工具不备份项目 `.env`。备份包含家庭隐私、密码哈希和聊天记录，归档文件权限为 600，仍须存到受限的异机存储。哈希用于发现损坏，不代表备份经过数字签名。

## 一、本地照片备份

在项目根目录、使用项目虚拟环境执行；默认从当前 `.env` 获取数据库及 `UPLOAD_DIR`：

```bash
.venv/bin/python backup.py create --output /secure-backups/memoir-2026-10-20.tar.gz
.venv/bin/python backup.py verify /secure-backups/memoir-2026-10-20.tar.gz
```

SQLite 使用在线 backup API，包含 WAL 中已提交的数据，不直接复制正在写入的数据库文件。MySQL 使用 `mysqldump --single-transaction`，要求原生客户端和 InnoDB；不支持把 SQLite 归档直接还原到 MySQL。

为保持数据库和照片一致，备份期间暂停新增、删除媒体和数据库结构变更。工具核对有效照片引用，缺失文件就失败，不能把缺照片的归档当成完整备份。

媒体归档范围为 `UPLOAD_DIR` 或显式指定的 `--media-dir` 内的普通文件；拒绝符号链接。不在这个目录中的原始采访录音、外部文件、代码和部署凭据须分别备份。已物理删除的文件不会被备份恢复。

## 二、OSS 照片备份

先用已授权的 OSS 工具或控制台导出私有桶对象到独立目录，保留对象 key 的目录结构。暂停媒体写入后，导出与数据库备份应在同一维护窗口完成：

```bash
.venv/bin/python backup.py create \
  --media-dir /secure-exports/memoir-objects \
  --output /secure-backups/memoir-oss-2026-10-20.tar.gz
.venv/bin/python backup.py verify /secure-backups/memoir-oss-2026-10-20.tar.gz
```

配置为 OSS 却没有提供对象导出目录时，工具拒绝创建备份，不会只备数据库就报告成功。生产桶仍需自行配置版本保留、异地备份与定期导出；本工具不会修改云账号或桶策略。

## 三、SQLite 隔离恢复

建立独立的 `/secure/memoir-restore.env`（不要覆盖生产 `.env`）：

```dotenv
DATABASE_URL=sqlite:////tmp/memoir-drill/restored.db
STORAGE_BACKEND=local
```

目标数据库与媒体目录都必须不存在：

```bash
.venv/bin/python backup.py --env-file /secure/memoir-restore.env restore \
  /secure-backups/memoir-2026-10-20.tar.gz \
  --media-dir /tmp/memoir-drill/restored-uploads
```

工具先验证归档清单、哈希和 SQLite 完整性，再创建目标。随后在隔离应用中显式配置 `DATABASE_URL`、`UPLOAD_DIR` 指向恢复目标，检查家庭、正文历史、照片、周报与权限。不要把恢复演练应用连回生产库。

## 四、MySQL 隔离恢复

安装与服务器版本匹配的 `mysql` / `mysqldump` 客户端，先建立独立空库。将其连接串放入单独恢复环境文件，不能把密码直接写进命令参数：

```dotenv
DATABASE_URL=mysql+pymysql://restore_user:URL编码后的密码@127.0.0.1:3306/memoir_restore?charset=utf8mb4
```

执行同样的 `backup.py --env-file ... restore ... --media-dir ...`。任何已有表或视图都会阻止恢复。凭据只写到权限 600 的短期客户端配置文件，执行后删除，不收入归档。

MySQL 导入失败可能留下部分表，工具不会主动删除目标库；排查后换新空库重试。SSL 等当前未适配的 URL 连接选项会明确拒绝，需使用已验证的数据库原生/托管备份方案，不能静默忽略连接安全配置。

OSS 归档的对象先恢复到指定媒体目录，再上传到独立私有桶，设置隔离应用的 OSS 配置，逐张验证。工具不会自动上传对象或修改生产桶。

## 五、升级与周期执行

1. 备份并验证，记录 Git 提交、环境配置位置、备份时间和恢复演练结果。
2. 在恢复副本执行 `migrate.py --dry-run` 和真实迁移，核对历史数据。
3. 维护窗口升级生产，再进行业务验收；结构迁移不能只靠回滚代码撤销。

建议至少每日备份、每次结构变更前额外备份，并按实际数据增长设置保留期；至少每月做一次隔离恢复。调度应由部署环境创建，命令成功后再传至异机存储，失败应告警。本次代码修改不替用户创建服务器定时任务。

## 六、自动验证

`python -m pytest -q` 包含 WAL、历史版本、照片恢复、校验失败、路径越界与拒绝覆盖测试。GitHub Actions 对 Python 3.10 / 3.12 执行 SQLite 回归，独立 MySQL 5.7 服务测试建表、增量迁移与原生备份恢复。

本机没有 MySQL 服务时，该集成用例会跳过；只有配置 `MEMOIR_TEST_MYSQL_ADMIN_URL` 才会创建并清理随机 `memoir_test_*` 数据库，不能把它指向生产。CI 通过需要实际运行结果确认，加入工作流不代表已经通过。
