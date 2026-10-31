CREATE TABLE IF NOT EXISTS interview_sessions (
 id varchar(64) NOT NULL PRIMARY KEY,
 family_id varchar(64) NOT NULL,
 user_id varchar(64) NOT NULL,
 revision integer NOT NULL DEFAULT 1,
 state varchar(16) NOT NULL DEFAULT 'active',
 topic varchar(16) NOT NULL DEFAULT 'childhood',
 followups integer NOT NULL DEFAULT 0,
 question varchar(512) NOT NULL,
 recording_mode varchar(16) NOT NULL DEFAULT 'unspecified',
 narrator_id varchar(64), subject_id varchar(64), narrator_label varchar(100), record_id varchar(64),
 create_by varchar(64), create_date datetime, update_by varchar(64), update_date datetime, remarks varchar(255), del_flag integer DEFAULT 0
);
CREATE INDEX ix_interview_sessions_user_id ON interview_sessions(user_id);
CREATE INDEX ix_interview_sessions_family_id ON interview_sessions(family_id);
CREATE TABLE IF NOT EXISTS interview_answers (
 id varchar(64) NOT NULL PRIMARY KEY,
 session_id varchar(64) NOT NULL,
 sequence integer NOT NULL,
 version integer NOT NULL DEFAULT 1,
 question varchar(512) NOT NULL,
 content mediumtext NOT NULL,
 kind varchar(16) NOT NULL DEFAULT 'text',
 history json,
 create_by varchar(64), create_date datetime, update_by varchar(64), update_date datetime, remarks varchar(255), del_flag integer DEFAULT 0,
 CONSTRAINT uq_interview_answer_sequence UNIQUE(session_id,sequence)
);
CREATE INDEX ix_interview_answers_session_id ON interview_answers(session_id);
