ALTER TABLE drafts ADD COLUMN voice_authorized_by varchar(64);
ALTER TABLE drafts ADD COLUMN voice_authorized_at datetime;
ALTER TABLE drafts ADD COLUMN voice_authorized_hash varchar(64);
CREATE TABLE IF NOT EXISTS `voice_profiles` (
  `family_id` VARCHAR(64) NOT NULL,
  `person_id` VARCHAR(64) NOT NULL,
  `epoch` INTEGER NOT NULL,
  `provider` VARCHAR(24) NOT NULL,
  `workspace_id` VARCHAR(80) NOT NULL,
  `model` VARCHAR(64) NOT NULL,
  `prefix` VARCHAR(10) NOT NULL,
  `status` VARCHAR(24) NOT NULL,
  `subject_state` VARCHAR(16) NOT NULL,
  `subject_user_id` VARCHAR(64) DEFAULT NULL,
  `reviewed_by` VARCHAR(64) DEFAULT NULL,
  `reviewed_at` DATETIME DEFAULT NULL,
  `evidence_ref` VARCHAR(80) DEFAULT NULL,
  `sample_key` VARCHAR(255) DEFAULT NULL,
  `provider_voice_id` VARCHAR(255) DEFAULT NULL,
  `uncertain` BOOL NOT NULL,
  `lease_token` VARCHAR(64) DEFAULT NULL,
  `lease_until` DATETIME DEFAULT NULL,
  `error_code` VARCHAR(32) DEFAULT NULL,
  `id` VARCHAR(64) NOT NULL,
  `create_by` VARCHAR(64) DEFAULT NULL,
  `create_date` DATETIME DEFAULT NULL,
  `update_by` VARCHAR(64) DEFAULT NULL,
  `update_date` DATETIME DEFAULT NULL,
  `remarks` VARCHAR(255) DEFAULT NULL,
  `del_flag` INTEGER DEFAULT NULL,
  PRIMARY KEY (`id`),
  CONSTRAINT `uq_voice_profiles_person_id` UNIQUE (`person_id`),
  CONSTRAINT `uq_voice_profiles_prefix` UNIQUE (`prefix`)
);
CREATE INDEX ix_voice_profiles_family_id ON `voice_profiles` (`family_id`);
CREATE TABLE IF NOT EXISTS `voice_consents` (
  `profile_id` VARCHAR(64) NOT NULL,
  `epoch` INTEGER NOT NULL,
  `user_id` VARCHAR(64) NOT NULL,
  `relation` VARCHAR(32) NOT NULL,
  `version` VARCHAR(32) NOT NULL,
  `revoked_at` DATETIME DEFAULT NULL,
  `id` VARCHAR(64) NOT NULL,
  `create_by` VARCHAR(64) DEFAULT NULL,
  `create_date` DATETIME DEFAULT NULL,
  `update_by` VARCHAR(64) DEFAULT NULL,
  `update_date` DATETIME DEFAULT NULL,
  `remarks` VARCHAR(255) DEFAULT NULL,
  `del_flag` INTEGER DEFAULT NULL,
  PRIMARY KEY (`id`),
  CONSTRAINT `uq_voice_consent` UNIQUE (`profile_id`,`epoch`,`user_id`)
);
CREATE INDEX ix_voice_consents_profile_id ON `voice_consents` (`profile_id`);
CREATE TABLE IF NOT EXISTS `voice_audio` (
  `family_id` VARCHAR(64) NOT NULL,
  `profile_id` VARCHAR(64) NOT NULL,
  `epoch` INTEGER NOT NULL,
  `interview_id` VARCHAR(64) NOT NULL,
  `draft_id` VARCHAR(64) NOT NULL,
  `text_hash` VARCHAR(64) NOT NULL,
  `requested_by` VARCHAR(64) NOT NULL,
  `status` VARCHAR(24) NOT NULL,
  `storage_key` VARCHAR(255) DEFAULT NULL,
  `charge_id` VARCHAR(64) DEFAULT NULL,
  `lease_token` VARCHAR(64) DEFAULT NULL,
  `lease_until` DATETIME DEFAULT NULL,
  `error_code` VARCHAR(32) DEFAULT NULL,
  `id` VARCHAR(64) NOT NULL,
  `create_by` VARCHAR(64) DEFAULT NULL,
  `create_date` DATETIME DEFAULT NULL,
  `update_by` VARCHAR(64) DEFAULT NULL,
  `update_date` DATETIME DEFAULT NULL,
  `remarks` VARCHAR(255) DEFAULT NULL,
  `del_flag` INTEGER DEFAULT NULL,
  PRIMARY KEY (`id`)
);
CREATE INDEX ix_voice_audio_family_id ON `voice_audio` (`family_id`);
CREATE INDEX ix_voice_audio_interview_id ON `voice_audio` (`interview_id`);
CREATE INDEX ix_voice_audio_profile_id ON `voice_audio` (`profile_id`);
CREATE TABLE IF NOT EXISTS `voice_charges` (
  `family_id` VARCHAR(64) NOT NULL,
  `audio_id` VARCHAR(64) NOT NULL,
  `period` VARCHAR(7) NOT NULL,
  `characters` INTEGER NOT NULL,
  `status` VARCHAR(24) NOT NULL,
  `id` VARCHAR(64) NOT NULL,
  `create_by` VARCHAR(64) DEFAULT NULL,
  `create_date` DATETIME DEFAULT NULL,
  `update_by` VARCHAR(64) DEFAULT NULL,
  `update_date` DATETIME DEFAULT NULL,
  `remarks` VARCHAR(255) DEFAULT NULL,
  `del_flag` INTEGER DEFAULT NULL,
  PRIMARY KEY (`id`)
);
CREATE INDEX ix_voice_charges_audio_id ON `voice_charges` (`audio_id`);
CREATE INDEX ix_voice_charges_family_id ON `voice_charges` (`family_id`);
CREATE TABLE IF NOT EXISTS `voice_audit` (
  `profile_id` VARCHAR(64) NOT NULL,
  `action` VARCHAR(32) NOT NULL,
  `epoch` INTEGER NOT NULL,
  `id` VARCHAR(64) NOT NULL,
  `create_by` VARCHAR(64) DEFAULT NULL,
  `create_date` DATETIME DEFAULT NULL,
  `update_by` VARCHAR(64) DEFAULT NULL,
  `update_date` DATETIME DEFAULT NULL,
  `remarks` VARCHAR(255) DEFAULT NULL,
  `del_flag` INTEGER DEFAULT NULL,
  PRIMARY KEY (`id`)
);
CREATE INDEX ix_voice_audit_profile_id ON `voice_audit` (`profile_id`);
