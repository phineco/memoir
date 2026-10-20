-- 001_add_users_name.sql
-- 2026-10-20：为家人开通账号加「真实姓名」字段（对应 models.py User.name）。
-- migrate.py 会自动跳过已存在的列（用户若已手动跑过 ALTER，再跑一次是安全的）。
-- 注意：COMMENT 只在 MySQL 生效，SQLite 下 migrate.py 会自动去掉。

ALTER TABLE users ADD COLUMN name varchar(64) DEFAULT NULL COMMENT '真实姓名';
