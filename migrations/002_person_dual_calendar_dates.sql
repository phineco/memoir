-- 2026-10-21: preserve independent partial solar/lunar dates; no calendar conversion.

ALTER TABLE persons ADD COLUMN birth_solar_year INTEGER DEFAULT NULL COMMENT '出生公历年';

ALTER TABLE persons ADD COLUMN birth_solar_month INTEGER DEFAULT NULL COMMENT '出生公历月';

ALTER TABLE persons ADD COLUMN birth_solar_day INTEGER DEFAULT NULL COMMENT '出生公历日';

ALTER TABLE persons ADD COLUMN birth_lunar_year INTEGER DEFAULT NULL COMMENT '出生农历年';

ALTER TABLE persons ADD COLUMN birth_lunar_month INTEGER DEFAULT NULL COMMENT '出生农历月';

ALTER TABLE persons ADD COLUMN birth_lunar_day INTEGER DEFAULT NULL COMMENT '出生农历日';

ALTER TABLE persons ADD COLUMN birth_lunar_leap BOOLEAN DEFAULT 0 COMMENT '出生农历是否闰月';

ALTER TABLE persons ADD COLUMN death_solar_year INTEGER DEFAULT NULL COMMENT '去世公历年';

ALTER TABLE persons ADD COLUMN death_solar_month INTEGER DEFAULT NULL COMMENT '去世公历月';

ALTER TABLE persons ADD COLUMN death_solar_day INTEGER DEFAULT NULL COMMENT '去世公历日';

ALTER TABLE persons ADD COLUMN death_lunar_year INTEGER DEFAULT NULL COMMENT '去世农历年';

ALTER TABLE persons ADD COLUMN death_lunar_month INTEGER DEFAULT NULL COMMENT '去世农历月';

ALTER TABLE persons ADD COLUMN death_lunar_day INTEGER DEFAULT NULL COMMENT '去世农历日';

ALTER TABLE persons ADD COLUMN death_lunar_leap BOOLEAN DEFAULT 0 COMMENT '去世农历是否闰月';

UPDATE persons SET birth_solar_year = birth_year WHERE birth_solar_year IS NULL AND birth_year IS NOT NULL AND COALESCE(birth_calendar, 'solar') = 'solar';

UPDATE persons SET birth_lunar_year = birth_year WHERE birth_lunar_year IS NULL AND birth_year IS NOT NULL AND COALESCE(birth_calendar, 'solar') = 'lunar';

UPDATE persons SET death_solar_year = death_year WHERE death_solar_year IS NULL AND death_year IS NOT NULL AND COALESCE(death_calendar, 'solar') = 'solar';

UPDATE persons SET death_lunar_year = death_year WHERE death_lunar_year IS NULL AND death_year IS NOT NULL AND COALESCE(death_calendar, 'solar') = 'lunar';
