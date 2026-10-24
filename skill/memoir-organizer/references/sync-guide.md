# sync-json 同步指南

> 目标：把 skill 产出的数据（家族树、初稿包、核实结果、修订）同步到网站后台入库。
> 网站侧已实现入库（`memoir-prototype/sync_engine.py` + `/f/<家庭>/sync` 页面 + `POST /api/sync`）。
> 契约原文见 `memoir-sync-design.md`；本文件是 skill 侧的**生成规则**，字段必须与网站解析逻辑一致。

## 一、数据包外壳（7 种 type 共用）

```json
{
  "type": "interview_upsert",
  "version": 1,
  "clientId": "uuid（每次新包重新生成，幂等去重用）",
  "updatedAt": "2026-10-17T16:05:00+08:00",
  "payload": { "...见下..." }
}
```

- `type` 枚举：`tree_upsert` / `interview_upsert` / `verification_update` / `new_person` / `person_status` / `revision_sync` / `plan_progress`。
- 输出时用 ```` ```sync-json ```` 代码块包裹，方便用户整段复制。
- 同一 `clientId` 重复导入会被网站自动跳过（返回"已入库"），所以**新包必须换新 uuid**，不要复用。

## 二、人物 id 稳定性（关键）

网站靠 id 把"这次讲的人"对应到树上人物，规则如下：

1. 建树时给**每个人分配一个稳定 id**（建议 `p01、p02…` 按辈分顺序，或"姓名拼音+序号"），之后该家庭内**同一人永远用同一 id**，跨多次对话保持一致。
2. 新出现的人物：先走 🆕 流程问用户是否入树；用户说入树 → 在下一次 `tree_upsert` 里带上他的 id 和信息；用户说不入/待定 → 用 `new_person` 单独同步。
3. **绝不复用**已删除人物的 id；**绝不编造** id 去对应不确定的人——对不上就走 🆕 或记待核实。
4. 讲述者确认沿用 organizing-guide §一.0：先问"这次是谁讲的"→ 对应到树上人物记 `narrator_person_id`；对应不上记 `narrator_name` 原文、`narrator_person_id` 留空。

## 三、触发时机

| 时机 | type |
|---|---|
| 建树完成 / 人物信息补全 / 状态变更 | `tree_upsert`（整树 persons 全量） |
| 整理/采访模式输出初稿包（四件套）时 | `interview_upsert` |
| 用户逐条确认/修正待核实项 | `verification_update` |
| 新人物出现并问完"是否入树" | `new_person`（入树则并入下一次 tree_upsert） |
| 人物状态 ⏳→📝→✅→✔️ 变更 | `person_status` |
| 应用完修订清单后 | `revision_sync` |
| 计划人物有进展（开始做→doing / 初稿完成→done） | `plan_progress` |

每次触发后主动问用户：**"是否同步到云端？"** → 用户说同步 → 输出数据包。

> **顺序要求（重要）**：新家庭第一次同步，必须**先发 `tree_upsert`、再发 `interview_upsert`**。
> 讲述对象（subject）只认 id 映射、没有姓名兜底（讲述者才有）；树还没同步建好映射就先发故事包，
> 故事会静默丢失讲述对象。同一轮里两个包都要发时，也按这个顺序逐个导入。

## 四、payload 模板

### 1. tree_upsert（整树）

```json
{
  "type": "tree_upsert", "version": 1, "clientId": "uuid", "updatedAt": "...",
  "payload": {
    "treeId": "tree_20261017_01",
    "persons": [
      {
        "id": "p02",
        "fullName": "王建军",
        "aliases": ["三叔"],
        "relation": "三叔",
        "birthYear": 1962, "deathYear": null, "alive": true,
        "status": "drafted",
        "notes": ["县城供销社上班", "爱下象棋"]
      }
    ]
  }
}
```

- `status` 枚举：`pending` ⏳待采访 / `doing` 📝整理中 / `drafted` ✅初稿完成 / `verified` ✔️已核实定稿。
- **`alive` 语义（网站三态生存状态，务必按此发）**：`true` = 健在；`false` = **已故**（网站直接记为去世，哪怕没有去世年份）；**状态未知就省略 `alive` 字段，绝不用 `false` 表示"不知道"**——发错会把活人标成去世。
- **历法冲突会整包被拒**：网站上人物已有公历/农历的详细月日时，只报年份且与已有日期对不上，整包导入失败。遇到失败先看网站错误原文，按提示核对该人物的日期再重发（见 §六.5）。
- 全名未知的人（如"三叔（待核实）"）**不要**放进 persons，网站会跳过；先走 `new_person`。
- 网站行为：已有人物→更新信息字段（不动家族树挂靠结构）；对不上的人→记入"待定新人物"，**不自动挂进树**。

### 2. interview_upsert（初稿包）

```json
{
  "type": "interview_upsert", "version": 1, "clientId": "uuid", "updatedAt": "...",
  "payload": {
    "topic": "供销社的那些年",
    "subject_person_id": "p02",
    "narrator_person_id": "p02",
    "narrator_name": "王建军",
    "period_start": "1978-01-01",
    "period_end": "1990-12-31",
    "period_precision": "year",
    "draft": "润色初稿全文……",
    "quotes": ["原话金句1", "原话金句2"],
    "verification_items": [{"text": "1985年是否已在供销社", "reason": "时间需确认"}],
    "timeline": [{"date": "1978", "event": "进县城供销社上班"}],
    "related_persons": [{"person_id": "p03", "role": "related"}]
  }
}
```

- `subject_person_id`：讲述对象（故事主角）的树上 id；`narrator_*` 见 §二.4。
- `period_precision`：`year` / `month` / `day`。
- `timeline[].date`：`"1978"`（年）/ `"1978-05"`（月）/ `"1978-05-01"`（日），网站自动识别精度。
- `related_persons[].role`：`related`（一般用这个）。
- 网站行为：**讲述对象只按 id 映射解析（无姓名兜底）**，对不上则讲述对象留空（先同步树，见 §三顺序要求）；讲述者按"映射→姓名"解析，对不上时名字记入备注不丢失；关联人物按映射解析。
- **入库即发布**：同步进来的故事在网站上直接是已发布状态（家庭成员可见）、不是草稿，核实与修订在网站侧继续。同步包目前不支持设置可见性，**私密故事不要走同步**，只在对话内交付。
- 金句、待核实文本超过 500 字会被网站截断，过长的请拆成两条。

### 3. verification_update（单条核实结果）

```json
{
  "type": "verification_update", "version": 1, "clientId": "uuid", "updatedAt": "...",
  "payload": {
    "interview_client_id": "当初 interview_upsert 的 clientId",
    "item_text": "1985年是否已在供销社（原文片段，需一字不差）",
    "status": "verified",
    "correction": "1983年进供销社（status=corrected 时填）"
  }
}
```

- 也可用 `interview_id`（网站侧 id）代替 `interview_client_id`，用 `item_id` 代替 `item_text`。
- `status`：`verified`（已确认）/ `corrected`（已修正，填 correction）。

### 4. new_person（新人物）

```json
{
  "type": "new_person", "version": 1, "clientId": "uuid", "updatedAt": "...",
  "payload": {"name": "王小明", "context": "三叔的儿子，在外地工作"}
}
```

### 5. person_status（状态变更）

```json
{
  "type": "person_status", "version": 1, "clientId": "uuid", "updatedAt": "...",
  "payload": {"person_id": "p02", "status": "verified"}
}
```

- 也可用 `name` 代替 `person_id`（姓名精确匹配）。

### 6. revision_sync（修订清单应用结果）

```json
{
  "type": "revision_sync", "version": 1, "clientId": "uuid", "updatedAt": "...",
  "payload": {
    "revisions": [
      {"kind": "verify", "interview_client_id": "uuid", "item_text": "原文片段", "action": "confirm"},
      {"kind": "verify", "interview_client_id": "uuid", "item_text": "原文片段", "action": "correct", "correction": "修正内容"},
      {"kind": "verify", "interview_client_id": "uuid", "item_text": "原文片段", "action": "skip"},
      {"kind": "draft", "interview_client_id": "uuid", "draft": "修订后的初稿全文"},
      {"kind": "person", "name": "三叔", "full_name": "王建军"}
    ]
  }
}
```

- `action`：`confirm` 确认 / `correct` 修正（填 correction）/ `skip` 转下周追问。
- `kind=draft`：全文修订，网站生成新版本（旧版本保留）。
- `kind=person`：正名（如"三叔→王建军"），旧名记入人物备注。

### 7. plan_progress（写作计划进度回写）

```json
{
  "type": "plan_progress", "version": 1, "clientId": "uuid", "updatedAt": "...",
  "payload": {
    "plan_id": "xxx（可空，空=当前计划）",
    "items": [
      {"person_name": "王建军", "status": "doing"},
      {"person_name": "王德顺", "status": "done"}
    ]
  }
}
```

- 人物匹配：**优先用 `person_name`**（最稳）；也可带 skill 侧 `person_id`（如 p01），网站走映射表解析，对不上会被忽略。
- `status` 只能是 `pending` / `doing` / `done`；只更新计划条目状态，不改顺序和备注。
- 触发：某计划人物的故事线本次有进展时，随本次同步节点一起输出。详细见 `references/writing-plan-guide.md`。

## 五、触发话术

输出数据包时，先说一句话，再贴代码块：

> 已生成同步数据包，复制下面 JSON 到网站「家庭管理 → 资料工具 → 同步入库」页导入：
> ```sync-json
> { … }
> ```
> 提醒：网站只显示已入库的数据，没导入的内容在页面上看不到。

## 六、诚实边界

1. 人物 id 对不上 → 走 🆕 / 记待核实，**绝不编造 id**。
2. 网站"人物解析"结果会在导入后告诉用户（更新了谁、谁没对上），如用户反馈没对上，检查 id 是否稳定一致。
3. 在 Muse 环境：按 storage-guide 落盘的同时，也可以输出 sync-json；其他模型 App 只输出 sync-json。
4. 修订与网站现有记录矛盾时（如网站已标已核实），**先指出，不静默覆盖**——以网站为唯一可信源。
5. **导入失败处理**：把网站返回的错误原文如实告诉用户，不假装成功。失败的数据包不会占用 `clientId`（网站以 failed 记录留痕），**修正数据后用同一个 `clientId` 重新生成整包再导入**，不要每次失败都换新 uuid；若其实已经入库成功，同 `clientId` 重发会被网站自动跳过，不会重复。
