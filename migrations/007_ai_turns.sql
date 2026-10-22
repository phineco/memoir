CREATE TABLE IF NOT EXISTS ai_turns (
  id varchar(64) NOT NULL PRIMARY KEY,
  family_id varchar(64) NOT NULL,
  user_id varchar(64) NOT NULL,
  question text NOT NULL,
  answer text,
  status varchar(16) NOT NULL,
  error varchar(255) DEFAULT NULL,
  sources json,
  context_stamp varchar(64) NOT NULL,
  lease_until datetime DEFAULT NULL,
  create_by varchar(64) DEFAULT NULL,
  create_date datetime DEFAULT NULL,
  update_by varchar(64) DEFAULT NULL,
  update_date datetime DEFAULT NULL,
  remarks varchar(255) DEFAULT NULL,
  del_flag int DEFAULT 0
);
