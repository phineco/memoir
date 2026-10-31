ALTER TABLE new_persons ADD COLUMN source_record_id varchar(64);
ALTER TABLE new_persons ADD COLUMN source_revision integer;
ALTER TABLE new_persons ADD COLUMN source_preview_revision integer;
ALTER TABLE new_persons ADD COLUMN evidence text;
ALTER TABLE new_persons ADD COLUMN linked_person_id varchar(64);
ALTER TABLE new_persons ADD COLUMN reviewed_by varchar(64);
