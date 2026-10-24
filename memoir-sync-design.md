# sync-json 同步协议

更新日期：2026-10-25。以 sync_engine.py 为执行实现，skill/memoir-organizer 为仓库附带的手动整理指南，不是 HTTP 客户端。

## 入口、鉴权与包格式

管理员从“家人 → 家庭管理 → 资料工具 → 同步入库”逐包导入；网页只接受一个 JSON 对象或一个 sync-json 代码块，多包或数组拒绝。

受控程序接入须另有已授权的管理员登录会话，POST /api/sync 请求体如下；无独立 API key/Bearer 接入，不让用户把 Cookie/密码交给外部助手。

```json
{
  "family_id": "website-family-id",
  "packet": {
    "type": "interview_upsert", "version": 1,
    "clientId": "globally-unique-packet-id",
    "payload": {"topic": "童年的河", "draft": "<p>故事初稿。</p>"}
  }
}
```

version 只接受整数 1，缺省兼容旧 v1；不是文章基础版本。updatedAt 不提供冲突控制。clientId 为全站唯一字符串（建议 UUID hex，最长 64 字符）；新操作用新 ID，同一操作重试保留原 ID。接口也兼容 family_id 与 type 同层格式。

## 权限与发布范围

- public 表示有效家庭成员可见，不是互联网公开。
- interview_upsert 新建已发布、家庭可见的故事；导入前须明确告知发布范围并获得用户同意。当前不提供草稿/私密导入，不能自行添加字段假定会生效。
- 已有故事正文及核实写入与网页共用整理权限：本人可整理；管理员只可额外整理无作者的家庭公开导入稿。指定读者或其他作者不因此获得写权限。
- 所有写入仍受家庭边界限制；文章有权限不代表普通成员可使用管理员同步入口。

## 人物身份与建树顺序

网站 Person.id 与外部 skill ID 是两个命名空间。映射只属于当前家庭，已有映射不能重绑其他人，删除人物后不能复用旧 skill ID。

1. 管理员先在家人页添加/核对真实人物；未匹配树包仅登记候选，不创建 Person 或亲属结构。
2. 用新的 tree_upsert 建立映射。persons[].id 为 skill ID，可加 site_person_id 明确选择网站人物，fullName 须与网站姓名/别名一致。
3. 核对结果后导入故事与进度。成功的候选包已占用 clientId，补齐人物后的绑定是新操作，须新包；不会自动补改旧故事。

姓名/别名仅在唯一匹配时回退，多候选整包拒绝。主角及关联人物只认映射，明确给出但未对应时拒绝；讲述者可凭唯一姓名回退，确实不明且未填 ID 时原称谓保存在备注。

## 七类 payload

| type | 字段与行为 |
|---|---|
| tree_upsert | persons: [{id, site_person_id?, fullName, aliases, birthYear, deathYear, alive, status, relation, notes}]；更新已有资料/映射，未知人物记候选 |
| interview_upsert | topic, draft, subject_person_id, narrator_person_id, narrator_name, period_start/end/precision, quotes, verification_items, timeline, related_persons；新包新建故事 |
| verification_update | interview_id 或 interview_client_id；item_id 或唯一 item_text；status, correction；更新有整理权限故事的核实项 |
| new_person | name 必需、context 可选；记录候选，不自动入树 |
| person_status | person_id（skill）/site_person_id（网站）/唯一 name，及 status；只改采访状态 |
| revision_sync | 非空 revisions 数组；核实、全文或正名，任一无效目标/动作整包回滚 |
| plan_progress | plan_id（null/省略取当前 active），非空 items: [{person_id 或 site_person_id 或唯一 person_name, status}]；无法对应到计划时整包拒绝 |

人物采访状态 pending/doing/drafted/verified；计划状态 pending/doing/done。计划 API 返回的网站 person_id 回写时放入 site_person_id，不能直接塞回 skill person_id。

alive=true 健在、false 已故，未知省略并保留旧状态。旧年份更新保护详细双历月日，冲突整包拒绝；完整日期走人物表单。treeId 不存储、不创建树，没有 generation 或 narrator_relation 字段。

故事日期用 YYYY-MM-DD，精度 year/month/day。时间轴 date 支持 YYYY/YYYY-MM/YYYY-MM-DD；未知时省略，把原始标签保留在 event/正文。金句、核实文字/原因最多保存 500 字，时间轴标题最多 128 字；超长资料生成前拆分并核对原文引用。

## 修订、图片与核实

```json
{
  "revisions": [
    {"kind":"verify","interview_id":"site-story-id","item_id":"verification-id","action":"correct","correction":"应为1979年"},
    {"kind":"draft","interview_client_id":"original-import-id","draft":"<p>修订全文。</p>","base_version":1,"revision_reason":"核对原始资料"},
    {"kind":"person","site_person_id":"site-person-id","full_name":"正确姓名"}
  ]
}
```

全文修订须有当前 base_version 和非空 revision_reason，与网页共用原子正文占用及历史保存。缺失或过期整包拒绝，不能猜版本或自动加版本重试。原始 clientId 引用当前家庭最初的故事入库包，不是本次修订包 ID。

初稿与全文修订共用网页家庭图片规则：保留合法相册引用；外部、跨家庭或不存在的图片拒绝。已删除照片显示占位并保留说明文字，不上传图片文件。

核实 verified/resolved/corrected 均保存 resolved；corrected/action=correct 必须有非空 correction，pending/action=skip 重新待核实。重复原文必须用 item_id 消歧，显式无效 ID 不回退到另一项。真正新解决时间由模型记录，重新打开时清除。

上线执行 015 数据迁移归一旧 corrected 状态，保留未知 resolved_at，不把迁移时间伪造为核实时间。旧图片损失、空人物关联和部分成功记录须人工核对，不自动改写历史故事。

## 结果与重试

- 成功：ok=true, applied=true，核对 summary；候选成功不等于已创建人物/关系。
- 重复：ok=true, applied=false，整包不重复执行。
- 协议、无效目标、无权整理或版本冲突：API HTTP 400，整包回滚并记录失败，核对后可用原 clientId 修正重试。
- 未登录 401，管理员不足 403，无家庭权限 404；不是“没有计划/没有资料”。
- 新版修订不再部分生效。升级前摘要包含“部分/跳过”的旧包需逐项人工对账，只对未生效部分生成新操作，不能整包换 UUID 重放。

GET /api/writing-plan?family_id=<id> 和 GET /api/weekly-report?family_id=<id>&year=<iso-year>&week=<week> 需有效成员会话，周报仅导出家庭 public 已发布故事。周报编号不是故事/核实项 ID，外部整理须保留对应关系。

同步不提供媒体/目录镜像、亲属结构自动创建、完整双历日期导入、人物小传写入或对外分享发布。
