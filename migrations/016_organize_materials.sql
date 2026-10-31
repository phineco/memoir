CREATE TABLE IF NOT EXISTS organize_records (
 id varchar(64) NOT NULL PRIMARY KEY, family_id varchar(64) NOT NULL,
 user_id varchar(64) NOT NULL, revision integer NOT NULL DEFAULT 1,
 topic varchar(128) NOT NULL, content mediumtext NOT NULL,
 narrator_id varchar(64), subject_id varchar(64), narrator_label varchar(100),
 preview json, preview_revision integer NOT NULL DEFAULT 0,
 preview_source_revision integer, story_id varchar(64),
 create_by varchar(64), create_date datetime, update_by varchar(64), update_date datetime,
 remarks varchar(255), del_flag integer DEFAULT 0
);
CREATE INDEX ix_organize_records_family_id ON organize_records (family_id);
CREATE INDEX ix_organize_records_user_id ON organize_records (user_id);
CREATE TABLE IF NOT EXISTS organize_sources (
 id varchar(64) NOT NULL PRIMARY KEY, record_id varchar(64) NOT NULL,
 revision integer NOT NULL, content mediumtext NOT NULL, identity json,
 create_by varchar(64), create_date datetime, update_by varchar(64), update_date datetime,
 remarks varchar(255), del_flag integer DEFAULT 0,
 CONSTRAINT uq_organize_source_version UNIQUE (record_id,revision)
);
CREATE INDEX ix_organize_sources_record_id ON organize_sources (record_id);
