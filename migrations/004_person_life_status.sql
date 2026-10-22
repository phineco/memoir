-- Preserve legacy values. Uncertain historical false values are reviewed, not inferred.
ALTER TABLE persons ADD COLUMN life_status varchar(16) DEFAULT NULL;
