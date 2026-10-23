ALTER TABLE ai_turns ADD COLUMN logical_id varchar(64);
ALTER TABLE verification_items ADD COLUMN resolved_at datetime;
CREATE INDEX ix_ai_turns_logical_id ON ai_turns (logical_id);
CREATE TABLE IF NOT EXISTS usage_events (
  id varchar(64) NOT NULL PRIMARY KEY, family_id varchar(64) NOT NULL, user_id varchar(64) NOT NULL,
  kind varchar(16) NOT NULL, outcome varchar(16) NOT NULL, duration_ms int NOT NULL,
  create_by varchar(64), create_date datetime, update_by varchar(64), update_date datetime,
  remarks varchar(255), del_flag int DEFAULT 0
);
CREATE INDEX ix_usage_events_user_id ON usage_events (user_id);
CREATE INDEX ix_usage_events_family_id ON usage_events (family_id);
CREATE INDEX ix_usage_actor_time ON usage_events (user_id,family_id,create_date);
CREATE INDEX ix_usage_events_create_date ON usage_events (create_date);
CREATE TABLE IF NOT EXISTS story_publications (
  id varchar(64) NOT NULL PRIMARY KEY, family_id varchar(64) NOT NULL,
  user_id varchar(64), published_at datetime NOT NULL,
  create_by varchar(64), create_date datetime, update_by varchar(64), update_date datetime,
  remarks varchar(255), del_flag int DEFAULT 0
);
CREATE INDEX ix_story_publications_family_id ON story_publications (family_id);
CREATE INDEX ix_story_publications_published_at ON story_publications (published_at);
CREATE TABLE IF NOT EXISTS metric_samples (
  id varchar(64) NOT NULL PRIMARY KEY, year int NOT NULL, week int NOT NULL,
  kind varchar(24) NOT NULL, task varchar(24) NOT NULL, device varchar(80), evidence_ref varchar(80) NOT NULL,
  sample_count int NOT NULL, success_count int NOT NULL, assisted_success int NOT NULL DEFAULT 0,
  void_reason varchar(32),
  create_by varchar(64), create_date datetime, update_by varchar(64), update_date datetime,
  remarks varchar(255), del_flag int DEFAULT 0,
  CONSTRAINT uq_metric_evidence UNIQUE (year,week,kind,task,evidence_ref)
);
