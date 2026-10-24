ALTER TABLE photos ADD COLUMN photo_month integer;
ALTER TABLE photos ADD COLUMN photo_day integer;
ALTER TABLE photos ADD COLUMN title varchar(120);
ALTER TABLE photos ADD COLUMN location varchar(255);
ALTER TABLE photos ADD COLUMN metadata_version integer NOT NULL DEFAULT 1;
CREATE INDEX ix_photos_family_time ON photos (family_id, del_flag, photo_year, photo_month, photo_day);
