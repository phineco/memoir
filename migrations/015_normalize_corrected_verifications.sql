-- Normalize legacy sync statuses without inventing historical resolution times.
UPDATE verification_items SET status = 'resolved' WHERE status = 'corrected';
