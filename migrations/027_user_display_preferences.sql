CREATE TABLE IF NOT EXISTS user_display_preferences (
 id varchar(64) NOT NULL PRIMARY KEY, user_id varchar(64) NOT NULL, revision integer NOT NULL DEFAULT 1,
 preferences json NOT NULL,
 create_by varchar(64), create_date datetime, update_by varchar(64), update_date datetime, remarks varchar(255), del_flag integer DEFAULT 0,
 CONSTRAINT uq_user_display_preference UNIQUE(user_id)
);
