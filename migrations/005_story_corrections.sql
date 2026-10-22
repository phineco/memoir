CREATE TABLE IF NOT EXISTS story_corrections (
  id varchar(64) NOT NULL PRIMARY KEY,
  interview_id varchar(64) NOT NULL,
  user_id varchar(64) NOT NULL,
  verification_id varchar(64) DEFAULT NULL,
  proposal text NOT NULL,
  evidence text,
  status varchar(16) DEFAULT 'pending',
  decision varchar(255) DEFAULT NULL,
  reviewed_by varchar(64) DEFAULT NULL,
  reviewed_at datetime DEFAULT NULL,
  create_by varchar(64) DEFAULT NULL,
  create_date datetime DEFAULT NULL,
  update_by varchar(64) DEFAULT NULL,
  update_date datetime DEFAULT NULL,
  remarks varchar(255) DEFAULT NULL,
  del_flag int DEFAULT 0
);
