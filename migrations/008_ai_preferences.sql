CREATE TABLE IF NOT EXISTS ai_preferences (
  id varchar(64) NOT NULL PRIMARY KEY,
  family_id varchar(64) NOT NULL,
  user_id varchar(64) NOT NULL,
  epoch varchar(32) NOT NULL,
  create_by varchar(64), create_date datetime,
  update_by varchar(64), update_date datetime,
  remarks varchar(255), del_flag int DEFAULT 0,
  CONSTRAINT uq_ai_preference UNIQUE (family_id,user_id)
);
