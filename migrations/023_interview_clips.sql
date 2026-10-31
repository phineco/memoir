CREATE TABLE IF NOT EXISTS interview_clips (
 id varchar(64) NOT NULL PRIMARY KEY, family_id varchar(64) NOT NULL, user_id varchar(64) NOT NULL,
 session_id varchar(64) NOT NULL, input_revision integer NOT NULL, question varchar(512) NOT NULL,
 source_hash varchar(64) NOT NULL, storage_key varchar(255) NOT NULL, duration_ms integer NOT NULL,
 status varchar(16) NOT NULL DEFAULT 'uploaded', answer_id varchar(64), transcript mediumtext, consent_asr boolean NOT NULL DEFAULT 0,
 model varchar(80), usage json, lease_token varchar(64), lease_until datetime,
 create_by varchar(64), create_date datetime, update_by varchar(64), update_date datetime, remarks varchar(255), del_flag integer DEFAULT 0
);
CREATE INDEX ix_interview_clips_session_id ON interview_clips(session_id);
CREATE INDEX ix_interview_clips_user_id ON interview_clips(user_id);
CREATE INDEX ix_interview_clips_family_id ON interview_clips(family_id);
