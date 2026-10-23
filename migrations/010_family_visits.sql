CREATE TABLE IF NOT EXISTS family_visits (
  id varchar(64) NOT NULL PRIMARY KEY,
  family_id varchar(64) NOT NULL, user_id varchar(64) NOT NULL,
  first_seen_at datetime NOT NULL, first_read_at datetime,
  first_saved_at datetime, first_published_at datetime,
  guide_status varchar(16) NOT NULL DEFAULT 'auto',
  cohort_eligible boolean NOT NULL DEFAULT 0,
  create_by varchar(64), create_date datetime,
  update_by varchar(64), update_date datetime,
  remarks varchar(255), del_flag int DEFAULT 0,
  CONSTRAINT uq_family_visit UNIQUE (family_id,user_id)
);
