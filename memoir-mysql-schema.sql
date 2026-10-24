-- ============================================================
-- 「家音」回忆录网站 · MySQL 5.7 新库基线（29 张业务表）
-- 日期：2026-10-20
-- 规范：每表含统一审计字段（id/create_by/create_date/update_by/
--       update_date/remarks/del_flag）；id 由应用生成（uuid/短id）；
--       del_flag 0=显示 1=隐藏；ENGINE=InnoDB CHARSET=utf8mb4
-- 配套：memoir-website-architecture.md §二 数据模型
-- 已确认：微信+手机号双绑定 / 阿里云OSS / 人物形象v1小传+照片墙 /
--         分享页 token+密码
-- ============================================================

-- 1. 用户（子女，付费/操作方）
CREATE TABLE `users` (
  `id` varchar(64) NOT NULL COMMENT '主键',
  `wechat_openid` varchar(64) DEFAULT NULL COMMENT '微信 openid',
  `phone` varchar(20) DEFAULT NULL COMMENT '手机号',
  `username` varchar(32) DEFAULT NULL COMMENT '用户名（管理员为家人开通）',
  `nickname` varchar(64) DEFAULT NULL COMMENT '昵称',
  `name` varchar(64) DEFAULT NULL COMMENT '真实姓名',
  `password_hash` varchar(128) DEFAULT NULL COMMENT '密码哈希',
  `create_by` varchar(64) DEFAULT NULL COMMENT '创建者',
  `create_date` datetime DEFAULT NULL COMMENT '创建时间',
  `update_by` varchar(64) DEFAULT NULL COMMENT '更新者',
  `update_date` datetime DEFAULT NULL COMMENT '更新时间',
  `remarks` varchar(255) DEFAULT NULL COMMENT '备注信息',
  `del_flag` int(11) DEFAULT NULL COMMENT '逻辑删除标记（0：显示；1：隐藏）',
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_openid` (`wechat_openid`),
  UNIQUE KEY `uk_phone` (`phone`),
  UNIQUE KEY `uk_username` (`username`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='用户表';

-- 2. 家庭（一棵家族树）
CREATE TABLE `families` (
  `id` varchar(64) NOT NULL COMMENT '主键',
  `name` varchar(64) DEFAULT NULL COMMENT '家庭名称，如王家',
  `owner_user_id` varchar(64) DEFAULT NULL COMMENT '所属用户 id',
  `create_by` varchar(64) DEFAULT NULL COMMENT '创建者',
  `create_date` datetime DEFAULT NULL COMMENT '创建时间',
  `update_by` varchar(64) DEFAULT NULL COMMENT '更新者',
  `update_date` datetime DEFAULT NULL COMMENT '更新时间',
  `remarks` varchar(255) DEFAULT NULL COMMENT '备注信息',
  `del_flag` int(11) DEFAULT NULL COMMENT '逻辑删除标记（0：显示；1：隐藏）',
  PRIMARY KEY (`id`),
  KEY `idx_owner` (`owner_user_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='家庭表';

-- 3. 人物（家族树节点，树形结构，参考 sys_area 模式）
-- 约定：parent_id = 在树中挂靠的上一代人物 id；根节点（家庭起点人物）parent_id='0'
--      parent_ids = 祖先路径，逗号分隔，如 '0,p01,p03,'，查后代用 LIKE '%,p01,%'
--      配偶挂靠到其配偶节点；同胞按 sort 排序
CREATE TABLE `persons` (
  `id` varchar(64) NOT NULL COMMENT '编号',
  `parent_id` varchar(64) NOT NULL DEFAULT '0' COMMENT '父级编号',
  `parent_ids` varchar(2000) NOT NULL DEFAULT '0,' COMMENT '所有父级编号',
  `family_id` varchar(64) DEFAULT NULL COMMENT '家庭 id',
  `name` varchar(100) NOT NULL COMMENT '名称（全名）',
  `aliases` json DEFAULT NULL COMMENT '曾用称谓数组，如["三叔"]',
  `relation` varchar(64) DEFAULT NULL COMMENT '与起点人物的关系',
  `generation` int(11) DEFAULT NULL COMMENT '辈分层级（0=起点本人）',
  `birth_year` int(11) DEFAULT NULL COMMENT '出生年份',
  `death_year` int(11) DEFAULT NULL COMMENT '去世年份',
  `birth_calendar` varchar(8) DEFAULT 'solar' COMMENT '出生历法 solar公历/lunar农历',
  `death_calendar` varchar(8) DEFAULT 'solar' COMMENT '去世历法 solar公历/lunar农历',
  `birth_solar_year` int(11) DEFAULT NULL COMMENT '出生公历年',
  `birth_solar_month` int(11) DEFAULT NULL COMMENT '出生公历月',
  `birth_solar_day` int(11) DEFAULT NULL COMMENT '出生公历日',
  `birth_lunar_year` int(11) DEFAULT NULL COMMENT '出生农历年',
  `birth_lunar_month` int(11) DEFAULT NULL COMMENT '出生农历月',
  `birth_lunar_day` int(11) DEFAULT NULL COMMENT '出生农历日',
  `birth_lunar_leap` tinyint(1) DEFAULT '0' COMMENT '出生农历是否闰月',
  `death_solar_year` int(11) DEFAULT NULL COMMENT '去世公历年',
  `death_solar_month` int(11) DEFAULT NULL COMMENT '去世公历月',
  `death_solar_day` int(11) DEFAULT NULL COMMENT '去世公历日',
  `death_lunar_year` int(11) DEFAULT NULL COMMENT '去世农历年',
  `death_lunar_month` int(11) DEFAULT NULL COMMENT '去世农历月',
  `death_lunar_day` int(11) DEFAULT NULL COMMENT '去世农历日',
  `death_lunar_leap` tinyint(1) DEFAULT '0' COMMENT '去世农历是否闰月',
  `alive` tinyint(1) DEFAULT NULL COMMENT '是否健在（1 是/0 否）',
  `life_status` varchar(16) DEFAULT NULL,
  `status` varchar(16) DEFAULT NULL COMMENT 'pending待采访/doing整理中/drafted初稿完成/verified已核实',
  `notes` json DEFAULT NULL COMMENT '备注线索数组，如["县城供销社上班"]',
  `sort` decimal(10,0) NOT NULL DEFAULT 0 COMMENT '排序（同级内）',
  `user_id` varchar(64) DEFAULT NULL COMMENT '关联登录用户 id（认领人物）',
  `gender` varchar(8) DEFAULT NULL COMMENT '性别 M/F',
  `spouse_id` varchar(64) DEFAULT NULL COMMENT '配偶人物 id（双向）',
  `create_by` varchar(64) DEFAULT NULL COMMENT '创建者',
  `create_date` datetime DEFAULT NULL COMMENT '创建时间',
  `update_by` varchar(64) DEFAULT NULL COMMENT '更新者',
  `update_date` datetime DEFAULT NULL COMMENT '更新时间',
  `remarks` varchar(255) DEFAULT NULL COMMENT '备注信息',
  `del_flag` int(11) DEFAULT NULL COMMENT '逻辑删除标记（0：显示；1：隐藏）',
  PRIMARY KEY (`id`),
  KEY `persons_parent_id` (`parent_id`),
  KEY `persons_family` (`family_id`),
  KEY `persons_del_flag` (`del_flag`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 ROW_FORMAT=DYNAMIC COMMENT='人物表';

-- 4. 源文件（每次上传一条，不可变，只追加）
CREATE TABLE `source_files` (
  `id` varchar(64) NOT NULL COMMENT '主键',
  `family_id` varchar(64) DEFAULT NULL COMMENT '家庭 id',
  `uploader_id` varchar(64) DEFAULT NULL COMMENT '上传者用户 id',
  `file_name` varchar(255) DEFAULT NULL COMMENT '原始文件名',
  `file_type` varchar(16) DEFAULT NULL COMMENT 'audio/video/text',
  `file_size` bigint(20) DEFAULT NULL COMMENT '文件大小（字节）',
  `duration_sec` int(11) DEFAULT NULL COMMENT '音视频时长（秒）',
  `storage_path` varchar(512) DEFAULT NULL COMMENT '阿里云 OSS 路径',
  `file_hash` varchar(64) DEFAULT NULL COMMENT '文件 hash，用于去重',
  `create_by` varchar(64) DEFAULT NULL COMMENT '创建者',
  `create_date` datetime DEFAULT NULL COMMENT '创建时间',
  `update_by` varchar(64) DEFAULT NULL COMMENT '更新者',
  `update_date` datetime DEFAULT NULL COMMENT '更新时间',
  `remarks` varchar(255) DEFAULT NULL COMMENT '备注信息',
  `del_flag` int(11) DEFAULT NULL COMMENT '逻辑删除标记（0：显示；1：隐藏）',
  PRIMARY KEY (`id`),
  KEY `idx_family_time` (`family_id`, `create_date`),
  KEY `idx_hash` (`file_hash`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='源文件表';

-- 5. 转写版本（同一源文件可多版）
CREATE TABLE `transcripts` (
  `id` varchar(64) NOT NULL COMMENT '主键',
  `source_file_id` varchar(64) DEFAULT NULL COMMENT '源文件 id',
  `version` int(11) DEFAULT NULL COMMENT '版本号（1=ASR，2+=人工校对）',
  `content` mediumtext COMMENT '文字稿全文',
  `asr_engine` varchar(64) DEFAULT NULL COMMENT 'ASR 引擎/人工校对标记',
  `confidence` decimal(5,4) DEFAULT NULL COMMENT '转写平均置信度',
  `create_by` varchar(64) DEFAULT NULL COMMENT '创建者',
  `create_date` datetime DEFAULT NULL COMMENT '创建时间',
  `update_by` varchar(64) DEFAULT NULL COMMENT '更新者',
  `update_date` datetime DEFAULT NULL COMMENT '更新时间',
  `remarks` varchar(255) DEFAULT NULL COMMENT '备注信息',
  `del_flag` int(11) DEFAULT NULL COMMENT '逻辑删除标记（0：显示；1：隐藏）',
  PRIMARY KEY (`id`),
  KEY `idx_source_ver` (`source_file_id`, `version`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='转写版本表';

-- 6. 整理任务（一次 AI 整理）
CREATE TABLE `interviews` (
  `id` varchar(64) NOT NULL COMMENT '主键',
  `family_id` varchar(64) DEFAULT NULL COMMENT '家庭 id',
  `source_file_id` varchar(64) DEFAULT NULL COMMENT '源文件 id',
  `transcript_id` varchar(64) DEFAULT NULL COMMENT '使用的转写版本 id',
  `person_id` varchar(64) DEFAULT NULL COMMENT '本次讲述对象人物 id',
  `topic` varchar(128) DEFAULT NULL COMMENT '主题，如童年',
  `prompt_version` varchar(32) DEFAULT NULL COMMENT '整理 prompt 版本号',
  `llm_model` varchar(64) DEFAULT NULL COMMENT 'LLM 模型标识',
  `status` varchar(16) DEFAULT NULL COMMENT 'processing/done/failed',
  `view_count` int(11) DEFAULT 0 COMMENT '观看数',
  `like_count` int(11) DEFAULT 0 COMMENT '点赞数',
  `period_start` date DEFAULT NULL COMMENT '故事时间段起',
  `period_end` date DEFAULT NULL COMMENT '故事时间段止',
  `period_precision` varchar(8) DEFAULT NULL COMMENT '时间精度 year/month/day',
  `author_id` varchar(64) DEFAULT NULL COMMENT '作者用户 id（手写文章）',
  `published_at` datetime DEFAULT NULL,
  `publish_status` varchar(16) DEFAULT NULL COMMENT 'draft草稿/published已发布',
  `visibility` varchar(16) DEFAULT 'public' COMMENT '可见性 public家庭可见/private仅作者/specific指定人',
  `narrator_person_id` varchar(64) DEFAULT NULL COMMENT '讲述者人物 id',
  `create_by` varchar(64) DEFAULT NULL COMMENT '创建者',
  `create_date` datetime DEFAULT NULL COMMENT '创建时间',
  `update_by` varchar(64) DEFAULT NULL COMMENT '更新者',
  `update_date` datetime DEFAULT NULL COMMENT '更新时间',
  `remarks` varchar(255) DEFAULT NULL COMMENT '备注信息',
  `del_flag` int(11) DEFAULT NULL COMMENT '逻辑删除标记（0：显示；1：隐藏）',
  PRIMARY KEY (`id`),
  KEY `idx_family` (`family_id`),
  KEY `idx_source` (`source_file_id`),
  KEY `idx_narrator` (`narrator_person_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='整理任务表';

-- 6.5 故事指定可见人

CREATE TABLE `interview_viewers` (
  `id` varchar(64) NOT NULL COMMENT '主键',
  `interview_id` varchar(64) DEFAULT NULL COMMENT '故事 id',
  `user_id` varchar(64) DEFAULT NULL COMMENT '可见用户 id',
  `create_by` varchar(64) DEFAULT NULL COMMENT '创建者',
  `create_date` datetime DEFAULT NULL COMMENT '创建时间',
  `update_by` varchar(64) DEFAULT NULL COMMENT '更新者',
  `update_date` datetime DEFAULT NULL COMMENT '更新时间',
  `remarks` varchar(255) DEFAULT NULL COMMENT '备注信息',
  `del_flag` int(11) DEFAULT NULL COMMENT '逻辑删除标记（0：显示；1：隐藏）',
  PRIMARY KEY (`id`),
  KEY `idx_interview` (`interview_id`),
  KEY `idx_user` (`user_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='故事指定可见人白名单';

-- 7. 初稿版本
CREATE TABLE `drafts` (
  `id` varchar(64) NOT NULL COMMENT '主键',
  `interview_id` varchar(64) DEFAULT NULL COMMENT '整理任务 id',
  `version` int(11) DEFAULT NULL COMMENT '版本号',
  `content` mediumtext COMMENT '初稿全文',
  `search_text` mediumtext,
  `voice_authorized_by` varchar(64) DEFAULT NULL,
  `voice_authorized_at` datetime DEFAULT NULL,
  `voice_authorized_hash` varchar(64) DEFAULT NULL,
  `is_current` tinyint(1) DEFAULT NULL COMMENT '是否为当前版（1 是）',
  `create_by` varchar(64) DEFAULT NULL COMMENT '创建者',
  `create_date` datetime DEFAULT NULL COMMENT '创建时间',
  `update_by` varchar(64) DEFAULT NULL COMMENT '更新者',
  `update_date` datetime DEFAULT NULL COMMENT '更新时间',
  `remarks` varchar(255) DEFAULT NULL COMMENT '备注信息',
  `del_flag` int(11) DEFAULT NULL COMMENT '逻辑删除标记（0：显示；1：隐藏）',
  PRIMARY KEY (`id`),
  KEY `idx_interview_ver` (`interview_id`, `version`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='初稿版本表';

-- 8. 金句
CREATE TABLE `quotes` (
  `id` varchar(64) NOT NULL COMMENT '主键',
  `interview_id` varchar(64) DEFAULT NULL COMMENT '整理任务 id',
  `text` varchar(512) DEFAULT NULL COMMENT '金句原文（原话）',
  `status` varchar(16) DEFAULT NULL COMMENT 'pending/kept/dropped',
  `create_by` varchar(64) DEFAULT NULL COMMENT '创建者',
  `create_date` datetime DEFAULT NULL COMMENT '创建时间',
  `update_by` varchar(64) DEFAULT NULL COMMENT '更新者',
  `update_date` datetime DEFAULT NULL COMMENT '更新时间',
  `remarks` varchar(255) DEFAULT NULL COMMENT '备注信息',
  `del_flag` int(11) DEFAULT NULL COMMENT '逻辑删除标记（0：显示；1：隐藏）',
  PRIMARY KEY (`id`),
  KEY `idx_interview` (`interview_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='金句表';

-- 9. 待核实清单
CREATE TABLE `verification_items` (
  `id` varchar(64) NOT NULL COMMENT '主键',
  `interview_id` varchar(64) DEFAULT NULL COMMENT '整理任务 id',
  `text` varchar(512) DEFAULT NULL COMMENT '存疑片段原文',
  `reason` varchar(512) DEFAULT NULL COMMENT '需核实的原因',
  `person_id` varchar(64) DEFAULT NULL COMMENT '已对应到树上的人物 id（可空）',
  `status` varchar(16) DEFAULT NULL COMMENT 'pending/resolved',
  `correction` varchar(512) DEFAULT NULL COMMENT '核实后的修正文字',
  `resolved_at` datetime DEFAULT NULL COMMENT '本次实际解决时间；历史未知不补造',
  `create_by` varchar(64) DEFAULT NULL COMMENT '创建者',
  `create_date` datetime DEFAULT NULL COMMENT '创建时间',
  `update_by` varchar(64) DEFAULT NULL COMMENT '更新者',
  `update_date` datetime DEFAULT NULL COMMENT '更新时间',
  `remarks` varchar(255) DEFAULT NULL COMMENT '备注信息',
  `del_flag` int(11) DEFAULT NULL COMMENT '逻辑删除标记（0：显示；1：隐藏）',
  PRIMARY KEY (`id`),
  KEY `idx_interview` (`interview_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='待核实清单表';

-- 10. 故事人物对应（称谓 ↔ 树上人物）
CREATE TABLE `person_links` (
  `id` varchar(64) NOT NULL COMMENT '主键',
  `interview_id` varchar(64) DEFAULT NULL COMMENT '整理任务 id',
  `mention` varchar(64) DEFAULT NULL COMMENT '故事中出现的称谓/名字',
  `person_id` varchar(64) DEFAULT NULL COMMENT '对应人物 id（空=新出现人物）',
  `is_new` tinyint(1) DEFAULT NULL COMMENT '是否新出现人物（1 是）',
  `status` varchar(16) DEFAULT NULL COMMENT 'linked/pending_confirm',
  `create_by` varchar(64) DEFAULT NULL COMMENT '创建者',
  `create_date` datetime DEFAULT NULL COMMENT '创建时间',
  `update_by` varchar(64) DEFAULT NULL COMMENT '更新者',
  `update_date` datetime DEFAULT NULL COMMENT '更新时间',
  `remarks` varchar(255) DEFAULT NULL COMMENT '备注信息',
  `del_flag` int(11) DEFAULT NULL COMMENT '逻辑删除标记（0：显示；1：隐藏）',
  PRIMARY KEY (`id`),
  KEY `idx_interview` (`interview_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='故事人物对应表';

-- 11. 新出现人物
CREATE TABLE `new_persons` (
  `id` varchar(64) NOT NULL COMMENT '主键',
  `family_id` varchar(64) DEFAULT NULL COMMENT '家庭 id',
  `interview_id` varchar(64) DEFAULT NULL COMMENT '来源整理任务 id',
  `name` varchar(64) DEFAULT NULL COMMENT '姓名/称谓',
  `context` varchar(512) DEFAULT NULL COMMENT '出现上下文',
  `join_tree` varchar(16) DEFAULT NULL COMMENT 'pending待定/joined已入树/dismissed仅备注',
  `create_by` varchar(64) DEFAULT NULL COMMENT '创建者',
  `create_date` datetime DEFAULT NULL COMMENT '创建时间',
  `update_by` varchar(64) DEFAULT NULL COMMENT '更新者',
  `update_date` datetime DEFAULT NULL COMMENT '更新时间',
  `remarks` varchar(255) DEFAULT NULL COMMENT '备注信息',
  `del_flag` int(11) DEFAULT NULL COMMENT '逻辑删除标记（0：显示；1：隐藏）',
  PRIMARY KEY (`id`),
  KEY `idx_family` (`family_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='新出现人物表';

-- 12. 时间轴事件
CREATE TABLE `timeline_events` (
  `id` varchar(64) NOT NULL COMMENT '主键',
  `family_id` varchar(64) DEFAULT NULL COMMENT '家庭 id',
  `person_id` varchar(64) DEFAULT NULL COMMENT '关联人物 id',
  `event_date` date DEFAULT NULL COMMENT '事件日期（精度不足时取当年1月1日/当月1日）',
  `date_precision` varchar(8) DEFAULT NULL COMMENT 'year/month/day',
  `title` varchar(128) DEFAULT NULL COMMENT '事件标题',
  `description` text COMMENT '事件描述',
  `source_interview_id` varchar(64) DEFAULT NULL COMMENT '来源整理任务 id',
  `create_by` varchar(64) DEFAULT NULL COMMENT '创建者',
  `create_date` datetime DEFAULT NULL COMMENT '创建时间',
  `update_by` varchar(64) DEFAULT NULL COMMENT '更新者',
  `update_date` datetime DEFAULT NULL COMMENT '更新时间',
  `remarks` varchar(255) DEFAULT NULL COMMENT '备注信息',
  `del_flag` int(11) DEFAULT NULL COMMENT '逻辑删除标记（0：显示；1：隐藏）',
  PRIMARY KEY (`id`),
  KEY `idx_family_date` (`family_id`, `event_date`),
  KEY `idx_person_date` (`person_id`, `event_date`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='时间轴事件表';

-- 13. 照片
CREATE TABLE `photos` (
  `id` varchar(64) NOT NULL COMMENT '主键',
  `family_id` varchar(64) DEFAULT NULL COMMENT '家庭 id',
  `person_id` varchar(64) DEFAULT NULL COMMENT '关联人物 id',
  `photo_month` int DEFAULT NULL,
  `metadata_version` int NOT NULL DEFAULT 1,
  `photo_day` int DEFAULT NULL,
  `title` varchar(120) DEFAULT NULL,
  `location` varchar(255) DEFAULT NULL,
  `photo_year` int(11) DEFAULT NULL COMMENT '拍摄年份（可估）',
  `event_id` varchar(64) DEFAULT NULL COMMENT '关联时间轴事件 id（可空）',
  `storage_path` varchar(512) DEFAULT NULL COMMENT '阿里云 OSS 路径',
  `caption` varchar(255) DEFAULT NULL COMMENT '照片说明',
  `uploaded_by` varchar(64) DEFAULT NULL COMMENT '上传者用户 id',
  `create_by` varchar(64) DEFAULT NULL COMMENT '创建者',
  `create_date` datetime DEFAULT NULL COMMENT '创建时间',
  `update_by` varchar(64) DEFAULT NULL COMMENT '更新者',
  `update_date` datetime DEFAULT NULL COMMENT '更新时间',
  `remarks` varchar(255) DEFAULT NULL COMMENT '备注信息',
  `del_flag` int(11) DEFAULT NULL COMMENT '逻辑删除标记（0：显示；1：隐藏）',
  PRIMARY KEY (`id`),
  KEY `idx_person_year` (`person_id`, `photo_year`),
  KEY `ix_photos_family_time` (`family_id`, `del_flag`, `photo_year`, `photo_month`, `photo_day`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='照片表';

-- 14. 人物形象（v1：小传；形象图 v2）
CREATE TABLE `portraits` (
  `id` varchar(64) NOT NULL COMMENT '主键',
  `person_id` varchar(64) DEFAULT NULL COMMENT '人物 id',
  `version` int(11) DEFAULT NULL COMMENT '版本号',
  `profile_text` mediumtext COMMENT 'AI 人物小传（每句带来源标注）',
  `generated_image_path` varchar(512) DEFAULT NULL COMMENT 'AI 形象图 OSS 路径（v2）',
  `create_by` varchar(64) DEFAULT NULL COMMENT '创建者',
  `create_date` datetime DEFAULT NULL COMMENT '创建时间',
  `update_by` varchar(64) DEFAULT NULL COMMENT '更新者',
  `update_date` datetime DEFAULT NULL COMMENT '更新时间',
  `remarks` varchar(255) DEFAULT NULL COMMENT '备注信息',
  `del_flag` int(11) DEFAULT NULL COMMENT '逻辑删除标记（0：显示；1：隐藏）',
  PRIMARY KEY (`id`),
  KEY `idx_person_ver` (`person_id`, `version`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='人物形象表';

-- 15. 分享快照（token + 密码，与业务库隔离）
CREATE TABLE `share_snapshots` (
  `id` varchar(64) NOT NULL COMMENT '主键',
  `family_id` varchar(64) DEFAULT NULL COMMENT '家庭 id',
  `title` varchar(128) DEFAULT NULL COMMENT '分享标题',
  `content_json` mediumtext COMMENT '冻结的快照内容 JSON',
  `token` varchar(64) DEFAULT NULL COMMENT '公开访问 token',
  `password_hash` varchar(128) DEFAULT NULL COMMENT '访问密码 bcrypt hash',
  `status` varchar(16) DEFAULT 'draft' COMMENT 'draft 待确认 / published 已发布',
  `expires_at` datetime DEFAULT NULL COMMENT '过期时间（可空=长期）',
  `create_by` varchar(64) DEFAULT NULL COMMENT '创建者',
  `create_date` datetime DEFAULT NULL COMMENT '创建时间',
  `update_by` varchar(64) DEFAULT NULL COMMENT '更新者',
  `update_date` datetime DEFAULT NULL COMMENT '更新时间',
  `remarks` varchar(255) DEFAULT NULL COMMENT '备注信息',
  `del_flag` int(11) DEFAULT NULL COMMENT '逻辑删除标记（0：显示；1：隐藏）',
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_token` (`token`),
  KEY `idx_family` (`family_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='分享快照表';

-- 16. 评论（树形结构，parent_id 挂靠，参考 persons/sys_area 模式）
CREATE TABLE `comments` (
  `id` varchar(64) NOT NULL COMMENT '编号',
  `interview_id` varchar(64) DEFAULT NULL COMMENT '文章（整理任务）id',
  `user_id` varchar(64) DEFAULT NULL COMMENT '评论者用户 id',
  `parent_id` varchar(64) NOT NULL DEFAULT '0' COMMENT '父级编号（0=顶层评论，否则为父评论 id）',
  `content` text COMMENT '评论内容',
  `like_count` int(11) DEFAULT 0 COMMENT '点赞数（缓存）',
  `create_by` varchar(64) DEFAULT NULL COMMENT '创建者',
  `create_date` datetime DEFAULT NULL COMMENT '创建时间',
  `update_by` varchar(64) DEFAULT NULL COMMENT '更新者',
  `update_date` datetime DEFAULT NULL COMMENT '更新时间',
  `remarks` varchar(255) DEFAULT NULL COMMENT '备注信息',
  `del_flag` int(11) DEFAULT NULL COMMENT '逻辑删除标记（0：显示；1：隐藏）',
  PRIMARY KEY (`id`),
  KEY `comments_interview` (`interview_id`),
  KEY `comments_parent` (`parent_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 ROW_FORMAT=DYNAMIC COMMENT='评论表';

-- 17. 点赞明细（一人一目标一条，软删=取消点赞）
CREATE TABLE `likes` (
  `id` varchar(64) NOT NULL COMMENT '主键',
  `target_type` varchar(16) DEFAULT NULL COMMENT '目标类型：interview/comment',
  `target_id` varchar(64) DEFAULT NULL COMMENT '目标 id',
  `user_id` varchar(64) DEFAULT NULL COMMENT '点赞用户 id',
  `create_by` varchar(64) DEFAULT NULL COMMENT '创建者',
  `create_date` datetime DEFAULT NULL COMMENT '创建时间',
  `update_by` varchar(64) DEFAULT NULL COMMENT '更新者',
  `update_date` datetime DEFAULT NULL COMMENT '更新时间',
  `remarks` varchar(255) DEFAULT NULL COMMENT '备注信息',
  `del_flag` int(11) DEFAULT NULL COMMENT '逻辑删除标记（0：显示；1：隐藏）',
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_like` (`target_type`, `target_id`, `user_id`),
  KEY `likes_target` (`target_type`, `target_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='点赞表';

-- 18. 故事关联人物（多对多）：讲述对象 + 相关人物，用于人物线串联
CREATE TABLE `interview_persons` (
  `id` varchar(64) NOT NULL COMMENT '主键',
  `interview_id` varchar(64) DEFAULT NULL COMMENT '故事（整理任务）id',
  `person_id` varchar(64) DEFAULT NULL COMMENT '人物 id',
  `role` varchar(16) DEFAULT NULL COMMENT '角色：subject=讲述对象，related=关联人物',
  `create_by` varchar(64) DEFAULT NULL COMMENT '创建者',
  `create_date` datetime DEFAULT NULL COMMENT '创建时间',
  `update_by` varchar(64) DEFAULT NULL COMMENT '更新者',
  `update_date` datetime DEFAULT NULL COMMENT '更新时间',
  `remarks` varchar(255) DEFAULT NULL COMMENT '备注信息',
  `del_flag` int(11) DEFAULT NULL COMMENT '逻辑删除标记（0：显示；1：隐藏）',
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_interview_person` (`interview_id`, `person_id`),
  KEY `ip_person` (`person_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='故事关联人物表';

-- interviews 表追加故事时间段（时间线串联）
-- interviews 表追加作者与发布状态（用户手写文章）
-- persons 表 user_id 索引（"这是我"认领查询用；列已在 CREATE TABLE 中）
CREATE INDEX `idx_persons_user` ON `persons` (`user_id`);

-- 家庭成员与角色（一个家庭可有多个管理员；权限按家庭隔离）
CREATE TABLE IF NOT EXISTS `family_members` (
  `id` varchar(64) NOT NULL COMMENT '主键',
  `family_id` varchar(64) DEFAULT NULL COMMENT '家庭 id',
  `user_id` varchar(64) DEFAULT NULL COMMENT '用户 id',
  `role` varchar(16) DEFAULT 'member' COMMENT 'owner=创建者 admin=管理员 member=普通成员',
  `create_by` varchar(64) DEFAULT NULL COMMENT '创建者',
  `create_date` datetime DEFAULT NULL COMMENT '创建时间',
  `update_by` varchar(64) DEFAULT NULL COMMENT '更新者',
  `update_date` datetime DEFAULT NULL COMMENT '更新时间',
  `remarks` varchar(255) DEFAULT NULL COMMENT '备注信息',
  `del_flag` int(11) DEFAULT '0' COMMENT '逻辑删除标记（0：显示；1：隐藏）',
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_family_member` (`family_id`, `user_id`),
  KEY `idx_fm_family` (`family_id`),
  KEY `idx_fm_user` (`user_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='家庭成员与角色表';

-- 存量迁移：已有家庭的创建者记为 owner
INSERT INTO `family_members` (`id`, `family_id`, `user_id`, `role`, `create_date`)
SELECT REPLACE(UUID(), '-', ''), `id`, `owner_user_id`, 'owner', NOW()
FROM `families` WHERE `owner_user_id` IS NOT NULL AND `del_flag` = 0
ON DUPLICATE KEY UPDATE `role` = 'owner';

CREATE TABLE `sync_log` (
  `id` varchar(64) NOT NULL COMMENT '主键',
  `family_id` varchar(64) DEFAULT NULL COMMENT '家庭 id',
  `op_type` varchar(32) DEFAULT NULL COMMENT '数据包类型',
  `client_id` varchar(64) DEFAULT NULL COMMENT '幂等键（skill 生成）',
  `target_id` varchar(64) DEFAULT NULL COMMENT '落库主记录 id',
  `status` varchar(16) DEFAULT 'ok' COMMENT 'ok/skipped/failed',
  `summary` varchar(512) DEFAULT NULL COMMENT '入库结果摘要',
  `create_by` varchar(64) DEFAULT NULL COMMENT '创建者',
  `create_date` datetime DEFAULT NULL COMMENT '创建时间',
  `update_by` varchar(64) DEFAULT NULL COMMENT '更新者',
  `update_date` datetime DEFAULT NULL COMMENT '更新时间',
  `remarks` varchar(255) DEFAULT NULL COMMENT '备注信息',
  `del_flag` int(11) DEFAULT NULL COMMENT '逻辑删除标记（0：显示；1：隐藏）',
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_client` (`client_id`),
  KEY `idx_family` (`family_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='sync-json 同步日志';

CREATE TABLE `person_id_map` (
  `id` varchar(64) NOT NULL COMMENT '主键',
  `family_id` varchar(64) DEFAULT NULL COMMENT '家庭 id',
  `skill_id` varchar(64) DEFAULT NULL COMMENT 'skill 侧人物 id',
  `person_id` varchar(64) DEFAULT NULL COMMENT '本站 person_id',
  `create_by` varchar(64) DEFAULT NULL COMMENT '创建者',
  `create_date` datetime DEFAULT NULL COMMENT '创建时间',
  `update_by` varchar(64) DEFAULT NULL COMMENT '更新者',
  `update_date` datetime DEFAULT NULL COMMENT '更新时间',
  `remarks` varchar(255) DEFAULT NULL COMMENT '备注信息',
  `del_flag` int(11) DEFAULT NULL COMMENT '逻辑删除标记（0：显示；1：隐藏）',
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_map_family_skill` (`family_id`, `skill_id`),
  KEY `idx_family` (`family_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='skill 人物 id 映射表';

CREATE TABLE `ai_memories` (
  `id` varchar(64) NOT NULL COMMENT '主键',
  `family_id` varchar(64) DEFAULT NULL COMMENT '家庭 id',
  `user_id` varchar(64) DEFAULT NULL COMMENT '用户 id',
  `memory_key` varchar(32) DEFAULT 'profile' COMMENT '记忆键',
  `content` mediumtext COMMENT '记忆内容',
  `create_by` varchar(64) DEFAULT NULL COMMENT '创建者',
  `create_date` datetime DEFAULT NULL COMMENT '创建时间',
  `update_by` varchar(64) DEFAULT NULL COMMENT '更新者',
  `update_date` datetime DEFAULT NULL COMMENT '更新时间',
  `remarks` varchar(255) DEFAULT NULL COMMENT '备注信息',
  `del_flag` int(11) DEFAULT NULL COMMENT '逻辑删除标记（0：显示；1：隐藏）',
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_ai_mem` (`family_id`, `user_id`, `memory_key`),
  KEY `idx_user` (`user_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='AI 用户记忆';

CREATE TABLE `ai_messages` (
  `id` varchar(64) NOT NULL COMMENT '主键',
  `family_id` varchar(64) DEFAULT NULL COMMENT '家庭 id',
  `user_id` varchar(64) DEFAULT NULL COMMENT '用户 id',
  `role` varchar(16) DEFAULT NULL COMMENT 'user/assistant',
  `content` mediumtext COMMENT '消息内容',
  `create_by` varchar(64) DEFAULT NULL COMMENT '创建者',
  `create_date` datetime DEFAULT NULL COMMENT '创建时间',
  `update_by` varchar(64) DEFAULT NULL COMMENT '更新者',
  `update_date` datetime DEFAULT NULL COMMENT '更新时间',
  `remarks` varchar(255) DEFAULT NULL COMMENT '备注信息',
  `del_flag` int(11) DEFAULT NULL COMMENT '逻辑删除标记（0：显示；1：隐藏）',
  PRIMARY KEY (`id`),
  KEY `idx_user` (`family_id`, `user_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='AI 问答聊天记录';

CREATE TABLE `ai_cache` (
  `id` varchar(64) NOT NULL COMMENT '主键',
  `family_id` varchar(64) DEFAULT NULL COMMENT '家庭 id',
  `cache_key` varchar(128) DEFAULT NULL COMMENT '缓存键（如 weekly:wang:42）',
  `content` mediumtext COMMENT '缓存内容 JSON',
  `create_by` varchar(64) DEFAULT NULL COMMENT '创建者',
  `create_date` datetime DEFAULT NULL COMMENT '创建时间',
  `update_by` varchar(64) DEFAULT NULL COMMENT '更新者',
  `update_date` datetime DEFAULT NULL COMMENT '更新时间',
  `remarks` varchar(255) DEFAULT NULL COMMENT '备注信息',
  `del_flag` int(11) DEFAULT NULL COMMENT '逻辑删除标记（0：显示；1：隐藏）',
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_cache_key` (`cache_key`),
  KEY `idx_family` (`family_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='AI 生成结果缓存';

CREATE TABLE `writing_plans` (
  `id` varchar(64) NOT NULL COMMENT '主键',
  `family_id` varchar(64) DEFAULT NULL COMMENT '家庭 id',
  `title` varchar(128) DEFAULT NULL COMMENT '计划标题',
  `status` varchar(16) DEFAULT 'draft' COMMENT 'draft草稿/active当前/archived归档',
  `items` mediumtext COMMENT '计划条目 JSON',
  `create_by` varchar(64) DEFAULT NULL COMMENT '创建者',
  `create_date` datetime DEFAULT NULL COMMENT '创建时间',
  `update_by` varchar(64) DEFAULT NULL COMMENT '更新者',
  `update_date` datetime DEFAULT NULL COMMENT '更新时间',
  `remarks` varchar(255) DEFAULT NULL COMMENT '备注信息',
  `del_flag` int(11) DEFAULT NULL COMMENT '逻辑删除标记（0：显示；1：隐藏）',
  PRIMARY KEY (`id`),
  KEY `idx_family` (`family_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='写作/采访计划';

CREATE TABLE `sms_codes` (
  `id` varchar(64) NOT NULL COMMENT '主键',
  `phone` varchar(20) DEFAULT NULL COMMENT '手机号',
  `code` varchar(10) DEFAULT NULL COMMENT '验证码',
  `purpose` varchar(16) DEFAULT NULL COMMENT 'register注册/reset找回密码',
  `used` int(11) DEFAULT 0 COMMENT '是否已用',
  `expire_at` datetime DEFAULT NULL COMMENT '过期时间',
  `create_by` varchar(64) DEFAULT NULL COMMENT '创建者',
  `create_date` datetime DEFAULT NULL COMMENT '创建时间',
  `update_by` varchar(64) DEFAULT NULL COMMENT '更新者',
  `update_date` datetime DEFAULT NULL COMMENT '更新时间',
  `remarks` varchar(255) DEFAULT NULL COMMENT '备注信息',
  `del_flag` int(11) DEFAULT NULL COMMENT '逻辑删除标记（0：显示；1：隐藏）',
  PRIMARY KEY (`id`),
  KEY `idx_phone` (`phone`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='短信验证码';

CREATE TABLE `invites` (
  `id` varchar(64) NOT NULL COMMENT '主键',
  `family_id` varchar(64) DEFAULT NULL COMMENT '家庭 id',
  `code` varchar(16) DEFAULT NULL COMMENT '邀请码',
  `max_uses` int(11) DEFAULT 0 COMMENT '最大使用次数（0=不限）',
  `used_count` int(11) DEFAULT 0 COMMENT '已使用次数',
  `expire_at` datetime DEFAULT NULL COMMENT '过期时间',
  `create_by` varchar(64) DEFAULT NULL COMMENT '创建者',
  `create_date` datetime DEFAULT NULL COMMENT '创建时间',
  `update_by` varchar(64) DEFAULT NULL COMMENT '更新者',
  `update_date` datetime DEFAULT NULL COMMENT '更新时间',
  `remarks` varchar(255) DEFAULT NULL COMMENT '备注信息',
  `del_flag` int(11) DEFAULT NULL COMMENT '逻辑删除标记（0：显示；1：隐藏）',
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_code` (`code`),
  KEY `idx_family` (`family_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='家庭邀请码';

-- 29. 自行注册的协议确认记录（UTC）
CREATE TABLE `legal_acceptances` (
  `id` varchar(64) NOT NULL,
  `user_id` varchar(64) NOT NULL,
  `terms_version` varchar(32) NOT NULL,
  `privacy_version` varchar(32) NOT NULL,
  `accepted_at` datetime NOT NULL,
  `create_by` varchar(64) DEFAULT NULL,
  `create_date` datetime DEFAULT NULL,
  `update_by` varchar(64) DEFAULT NULL,
  `update_date` datetime DEFAULT NULL,
  `remarks` varchar(255) DEFAULT NULL,
  `del_flag` int DEFAULT 0,
  PRIMARY KEY (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='自行注册协议确认';

CREATE TABLE `story_corrections` (
  `id` varchar(64) NOT NULL PRIMARY KEY,
  `interview_id` varchar(64) NOT NULL,
  `user_id` varchar(64) NOT NULL,
  `verification_id` varchar(64) DEFAULT NULL,
  `proposal` text NOT NULL,
  `evidence` text,
  `status` varchar(16) DEFAULT 'pending',
  `decision` varchar(255) DEFAULT NULL,
  `reviewed_by` varchar(64) DEFAULT NULL,
  `reviewed_at` datetime DEFAULT NULL,
  `create_by` varchar(64) DEFAULT NULL,
  `create_date` datetime DEFAULT NULL,
  `update_by` varchar(64) DEFAULT NULL,
  `update_date` datetime DEFAULT NULL,
  `remarks` varchar(255) DEFAULT NULL,
  `del_flag` int DEFAULT 0
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE `ai_turns` (
  `id` varchar(64) NOT NULL PRIMARY KEY,
  `family_id` varchar(64) NOT NULL,
  `user_id` varchar(64) NOT NULL,
  `question` text NOT NULL,
  `logical_id` varchar(64) DEFAULT NULL,
  `answer` text,
  `status` varchar(16) NOT NULL,
  `error` varchar(255) DEFAULT NULL,
  `sources` json,
  `context_stamp` varchar(64) NOT NULL,
  `lease_until` datetime DEFAULT NULL,
  `create_by` varchar(64) DEFAULT NULL,
  `create_date` datetime DEFAULT NULL,
  `update_by` varchar(64) DEFAULT NULL,
  `update_date` datetime DEFAULT NULL,
  `remarks` varchar(255) DEFAULT NULL,
  `del_flag` int DEFAULT 0,
  KEY `ix_ai_turns_logical_id` (`logical_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE `ai_preferences` (
  `id` varchar(64) NOT NULL,
  `family_id` varchar(64) NOT NULL,
  `user_id` varchar(64) NOT NULL,
  `epoch` varchar(32) NOT NULL,
  `create_by` varchar(64) DEFAULT NULL,
  `create_date` datetime DEFAULT NULL,
  `update_by` varchar(64) DEFAULT NULL,
  `update_date` datetime DEFAULT NULL,
  `remarks` varchar(255) DEFAULT NULL,
  `del_flag` int DEFAULT 0,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_ai_preference` (`family_id`,`user_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='AI上下文重置边界';

CREATE TABLE `family_visits` (
  `id` varchar(64) NOT NULL,
  `family_id` varchar(64) NOT NULL,
  `user_id` varchar(64) NOT NULL,
  `first_seen_at` datetime NOT NULL,
  `first_read_at` datetime DEFAULT NULL,
  `first_saved_at` datetime DEFAULT NULL,
  `first_published_at` datetime DEFAULT NULL,
  `guide_status` varchar(16) NOT NULL DEFAULT 'auto',
  `cohort_eligible` boolean NOT NULL DEFAULT 0,
  `create_by` varchar(64) DEFAULT NULL,
  `create_date` datetime DEFAULT NULL,
  `update_by` varchar(64) DEFAULT NULL,
  `update_date` datetime DEFAULT NULL,
  `remarks` varchar(255) DEFAULT NULL,
  `del_flag` int DEFAULT 0,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_family_visit` (`family_id`,`user_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='个人家庭引导与首次观察';

CREATE TABLE `privacy_requests` (
  `id` varchar(64) NOT NULL,
  `user_id` varchar(64) NOT NULL,
  `kind` varchar(24) NOT NULL,
  `details` text NOT NULL,
  `status` varchar(16) NOT NULL,
  `revision` int NOT NULL DEFAULT 1,
  `first_response_at` datetime DEFAULT NULL,
  `identity_verified_at` datetime DEFAULT NULL,
  `resolved_at` datetime DEFAULT NULL,
  `create_by` varchar(64) DEFAULT NULL,
  `create_date` datetime DEFAULT NULL,
  `update_by` varchar(64) DEFAULT NULL,
  `update_date` datetime DEFAULT NULL,
  `remarks` varchar(255) DEFAULT NULL,
  `del_flag` int DEFAULT 0,
  PRIMARY KEY (`id`),
  KEY `ix_privacy_requests_user_id` (`user_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='隐私申请';

CREATE TABLE `privacy_responses` (
  `id` varchar(64) NOT NULL,
  `request_id` varchar(64) NOT NULL,
  `actor_role` varchar(16) NOT NULL,
  `revision` int NOT NULL,
  `status` varchar(16) NOT NULL,
  `content` text NOT NULL,
  `create_by` varchar(64) DEFAULT NULL,
  `create_date` datetime DEFAULT NULL,
  `update_by` varchar(64) DEFAULT NULL,
  `update_date` datetime DEFAULT NULL,
  `remarks` varchar(255) DEFAULT NULL,
  `del_flag` int DEFAULT 0,
  PRIMARY KEY (`id`),
  KEY `ix_privacy_responses_request_id` (`request_id`),
  UNIQUE KEY `uq_privacy_response_revision` (`request_id`,`revision`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='隐私申请处理记录';

CREATE TABLE `usage_events` (
  `id` varchar(64) NOT NULL,
  `family_id` varchar(64) NOT NULL,
  `user_id` varchar(64) NOT NULL,
  `kind` varchar(16) NOT NULL,
  `outcome` varchar(16) NOT NULL,
  `duration_ms` int NOT NULL,
  `create_by` varchar(64) DEFAULT NULL,
  `create_date` datetime DEFAULT NULL,
  `update_by` varchar(64) DEFAULT NULL,
  `update_date` datetime DEFAULT NULL,
  `remarks` varchar(255) DEFAULT NULL,
  `del_flag` int DEFAULT 0,
  PRIMARY KEY (`id`),
  KEY `ix_usage_events_user_id` (`user_id`),
  KEY `ix_usage_events_family_id` (`family_id`),
  KEY `ix_usage_actor_time` (`user_id`,`family_id`,`create_date`),
  KEY `ix_usage_events_create_date` (`create_date`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='浏览器状态样本';

CREATE TABLE `story_publications` (
  `id` varchar(64) NOT NULL,
  `family_id` varchar(64) NOT NULL,
  `user_id` varchar(64) DEFAULT NULL,
  `published_at` datetime NOT NULL,
  `create_by` varchar(64) DEFAULT NULL,
  `create_date` datetime DEFAULT NULL,
  `update_by` varchar(64) DEFAULT NULL,
  `update_date` datetime DEFAULT NULL,
  `remarks` varchar(255) DEFAULT NULL,
  `del_flag` int DEFAULT 0,
  PRIMARY KEY (`id`),
  KEY `ix_story_publications_family_id` (`family_id`),
  KEY `ix_story_publications_published_at` (`published_at`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='确定首次发布记录';

CREATE TABLE `metric_samples` (
  `id` varchar(64) NOT NULL,
  `year` int NOT NULL,
  `week` int NOT NULL,
  `kind` varchar(24) NOT NULL,
  `task` varchar(24) NOT NULL,
  `device` varchar(80) DEFAULT NULL,
  `evidence_ref` varchar(80) NOT NULL,
  `sample_count` int NOT NULL,
  `success_count` int NOT NULL,
  `assisted_success` int NOT NULL DEFAULT 0,
  `void_reason` varchar(32) DEFAULT NULL,
  `create_by` varchar(64) DEFAULT NULL,
  `create_date` datetime DEFAULT NULL,
  `update_by` varchar(64) DEFAULT NULL,
  `update_date` datetime DEFAULT NULL,
  `remarks` varchar(255) DEFAULT NULL,
  `del_flag` int DEFAULT 0,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_metric_evidence` (`year`,`week`,`kind`,`task`,`evidence_ref`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='真实人工指标样本';

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
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
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
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
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
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
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
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
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
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
CREATE INDEX ix_voice_audit_profile_id ON `voice_audit` (`profile_id`);
