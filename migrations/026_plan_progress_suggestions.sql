CREATE TABLE IF NOT EXISTS plan_progress_suggestions (
 id varchar(64) NOT NULL PRIMARY KEY, family_id varchar(64) NOT NULL, user_id varchar(64) NOT NULL,
 record_id varchar(64) NOT NULL, story_id varchar(64) NOT NULL, story_version integer NOT NULL,
 person_id varchar(64) NOT NULL, plan_id varchar(64) NOT NULL, item_index integer NOT NULL, plan_stamp varchar(64) NOT NULL,
 status varchar(16) NOT NULL DEFAULT 'pending', reviewed_by varchar(64),
 create_by varchar(64), create_date datetime, update_by varchar(64), update_date datetime, remarks varchar(255), del_flag integer DEFAULT 0
);
CREATE INDEX ix_plan_progress_suggestions_family_id ON plan_progress_suggestions(family_id);
