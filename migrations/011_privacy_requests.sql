CREATE TABLE IF NOT EXISTS privacy_requests (
  id varchar(64) NOT NULL PRIMARY KEY, user_id varchar(64) NOT NULL,
  kind varchar(24) NOT NULL, details text NOT NULL,
  status varchar(16) NOT NULL, revision int NOT NULL DEFAULT 1,
  first_response_at datetime, identity_verified_at datetime, resolved_at datetime,
  create_by varchar(64), create_date datetime,
  update_by varchar(64), update_date datetime,
  remarks varchar(255), del_flag int DEFAULT 0
);
CREATE INDEX ix_privacy_requests_user_id ON privacy_requests (user_id);
CREATE TABLE IF NOT EXISTS privacy_responses (
  id varchar(64) NOT NULL PRIMARY KEY, request_id varchar(64) NOT NULL,
  actor_role varchar(16) NOT NULL, revision int NOT NULL, status varchar(16) NOT NULL, content text NOT NULL,
  create_by varchar(64), create_date datetime,
  update_by varchar(64), update_date datetime,
  remarks varchar(255), del_flag int DEFAULT 0,
  CONSTRAINT uq_privacy_response_revision UNIQUE (request_id,revision)
);
CREATE INDEX ix_privacy_responses_request_id ON privacy_responses (request_id);
