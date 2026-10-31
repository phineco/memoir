CREATE TABLE IF NOT EXISTS organize_tasks (
 id varchar(64) NOT NULL PRIMARY KEY, family_id varchar(64) NOT NULL,
 user_id varchar(64) NOT NULL, record_id varchar(64) NOT NULL,
 input_revision integer NOT NULL, status varchar(16) NOT NULL,
 model varchar(80), prompt_version varchar(32), source_chars integer NOT NULL,
 result json, usage json, error_code varchar(32), lease_token varchar(64), lease_until datetime,
 create_by varchar(64), create_date datetime, update_by varchar(64), update_date datetime,
 remarks varchar(255), del_flag integer DEFAULT 0
);
CREATE INDEX ix_organize_tasks_family_id ON organize_tasks (family_id);
CREATE INDEX ix_organize_tasks_user_id ON organize_tasks (user_id);
CREATE INDEX ix_organize_tasks_record_id ON organize_tasks (record_id);
