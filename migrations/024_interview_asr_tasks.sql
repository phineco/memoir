CREATE TABLE IF NOT EXISTS interview_asr_tasks (
 id varchar(64) NOT NULL PRIMARY KEY, family_id varchar(64) NOT NULL, user_id varchar(64) NOT NULL,
 session_id varchar(64) NOT NULL, clip_id varchar(64) NOT NULL, status varchar(16) NOT NULL,
 model varchar(80) NOT NULL, duration_ms integer NOT NULL, usage json, lease_token varchar(64), lease_until datetime,
 create_by varchar(64), create_date datetime, update_by varchar(64), update_date datetime, remarks varchar(255), del_flag integer DEFAULT 0
);
CREATE INDEX ix_interview_asr_tasks_user_id ON interview_asr_tasks(user_id);
CREATE INDEX ix_interview_asr_tasks_family_id ON interview_asr_tasks(family_id);
CREATE INDEX ix_interview_asr_tasks_session_id ON interview_asr_tasks(session_id);
CREATE INDEX ix_interview_asr_tasks_clip_id ON interview_asr_tasks(clip_id);
