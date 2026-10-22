-- Unknown historical publication times remain NULL; displayed estimates use create_date.
ALTER TABLE interviews ADD COLUMN published_at datetime DEFAULT NULL;
