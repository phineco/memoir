-- Registration acknowledgement timestamps are UTC; no backfill of existing users.
CREATE TABLE IF NOT EXISTS legal_acceptances (
  id varchar(64) NOT NULL PRIMARY KEY,
  user_id varchar(64) NOT NULL,
  terms_version varchar(32) NOT NULL,
  privacy_version varchar(32) NOT NULL,
  accepted_at datetime NOT NULL,
  create_by varchar(64) DEFAULT NULL,
  create_date datetime DEFAULT NULL,
  update_by varchar(64) DEFAULT NULL,
  update_date datetime DEFAULT NULL,
  remarks varchar(255) DEFAULT NULL,
  del_flag int DEFAULT 0
);
