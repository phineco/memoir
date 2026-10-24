# sync-json 同步指南

> 目标：把 skill 产出的数据（家族树、初稿包、核实结果、修订）同步到网站后台入库。
> 网站侧已实现入库（`sync_engine.py` + `/f/<家庭>/sync` 页面 + `POST /api/sync`）。
> 本文件完整描述 skill 的手动导入契约，不依赖包外的文件。仓库中的 `memoir-sync-design.md` 是维护者参考；独立安装本 skill 无需该文件。

## 一、数据包外壳（7 种 type 共用）

```json
{
  "type": "interview_upsert",
  "version": 1,
  "clientId": "uuid（每次新包重新生成，幂等去重用）",
  "updatedAt": "2026-10-17T16:05:00+08:00",
  "payload": {}
}
```

- `type` 枚举：`tree_upsert` / `interview_upsert` / `verification_update` / `new_person` / `person_status` / `revision_sync` / `plan_progress`。
- 网站一次只接收一个 JSON 对象；多个代码块或数组会拒绝，请逐个导入并检查结果。
- `version` 仅支持整数 1；省略兼容旧 v1 包。`updatedAt` 不是正文版本，也不能防止覆盖。
- 输出时用 ```` ```sync-json ```` 代码块包裹，方便用户整段复制。
- 同一 `clientId` 重复导入会被网站自动跳过（返回"已入库"），所以**新包必须换新 uuid**，不要复用。

## 二、人物 id 稳定性（关键）

网站靠 id 把"这次讲的人"对应到树上人物，规则如下：

1. 建树时给**每个人分配一个稳定 id**（建议 `p01、p02…` 按辈分顺序，或"姓名拼音+序号"），之后该家庭内**同一人永远用同一 id**，跨多次对话保持一致。
2. 新出现的人物：先走 🆕 流程问用户是否入树；用户说入树 → 请管理员先在网站「家人 → 添加人物」建立/核对真实人物，再用新的 `tree_upsert` 包绑定稳定 id；`new_person` 和未匹配的树包只登记候选，不创建真实人物。
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

同步前说明范围：故事入库即全家可见，可能用于家庭周报与问 AI；确认用户愿意按该范围发布后，再输出数据包。私密内容仅在对话内交付。

**新家庭/新人物的顺序**：

1. 管理员先在「家人 → 添加人物」建立或核对网站真实人物。
2. 用新的 `tree_upsert` 包建立 skill id 映射；可提供 `site_person_id` 明确选择网站人物，`fullName` 需与网站姓名/别名一致。
3. 核对导入摘要：仍显示“待定”就先停止；真实人物创建后，原成功树包已被去重，须用新 `clientId` 提交新的绑定操作。
4. 映射成功后逐包导入故事、状态、计划，并检查每包结果。故事中提供但无法对应的主角/关联人物 ID 会整包拒绝，不再静默丢失关联。

主角/关联人物继续使用 skill id；网站 ID 不能直接塞进这些字段。讲述者可按唯一姓名回退；身份不明时不填 id，保留原称谓及待核实。旧故事不会因新增映射自动补关联，请回网页编辑核对，不要重复导入同一篇故事。

## 四、payload 模板

### 1. tree_upsert（整树）

```json
{
  "type": "tree_upsert", "version": 1, "clientId": "uuid", "updatedAt": "...",
  "payload": {
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

- 每个人可选 `site_person_id`（网站人物 ID，用于明确绑定）；`id` 始终是 skill ID。映射一旦建立不能用同一 skill ID 换人，人物删除后也不能复用。
- `status` 枚举：`pending` ⏳待采访 / `doing` 📝整理中 / `drafted` ✅初稿完成 / `verified` ✔️已核实定稿。
- **`alive` 语义（网站三态生存状态，务必按此发）**：`true` = 健在；`false` = **已故**（网站直接记为去世，哪怕没有去世年份）；**状态未知就省略 `alive` 字段，绝不用 `false` 表示"不知道"**——发错会把活人标成去世。
- **历法冲突会整包被拒**：网站上人物已有公历/农历的详细月日时，只报年份且与已有日期对不上，整包导入失败。遇到失败先看网站错误原文，按提示核对该人物的日期再重发（见 §六.6）。
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
- 时间不明时省略 `date`，把“小时候/有一年”等原始标签保留在 `event` 和正文，不编造年份。
- `timeline[].date`：`"1978"`（年）/ `"1978-05"`（月）/ `"1978-05-01"`（日），网站自动识别精度。
- `related_persons[].role`：`related`（一般用这个）。
- 网站行为：**讲述对象只按 id 映射解析（无姓名兜底）**，提供主角 ID 却对不上时整包拒绝（先建立映射，见 §三顺序要求）；讲述者按"映射→姓名"解析，对不上时名字记入备注不丢失；关联人物按映射解析。
- **入库即发布**：同步进来的故事在网站上直接是已发布状态（家庭成员可见）、不是草稿，核实与修订在网站侧继续。同步包不支持 visibility/publish_status/viewer_ids 等私密、草稿、指定人参数，携带这些字段会拒绝而不发布；**私密故事不要走同步**，只在对话内交付。
- 金句、待核实文本超过 500 字会被网站截断，过长的请拆成两条。

### 3. verification_update（单条核实结果）

```json
{
  "type": "verification_update", "version": 1, "clientId": "uuid", "updatedAt": "...",
  "payload": {
    "interview_client_id": "original-interview-packet",
    "item_text": "1985年是否已在供销社",
    "status": "corrected",
    "correction": "1983年进供销社"
  }
}
```

- `interview_client_id` 必须换为当初故事成功入库包的 clientId；`item_text` 使用当初保存的原文，不能附加解释。
- 也可用 `interview_id`（网站侧 id）代替 `interview_client_id`，用 `item_id` 代替 `item_text`。
- `status`：`verified`（已确认）/ `corrected`（已修正，必须填非空 correction），两者在网站统一存为 resolved 并显示已解决；pending 表示重新待核实。未知状态或空更正会整包拒绝。

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

- 也可用 `site_person_id` 明确指定网站人物，或用唯一 `name` 回退；姓名或别名对应多人时拒绝，不能取第一位。

### 6. revision_sync（修订清单应用结果）

```json
{
  "type": "revision_sync", "version": 1, "clientId": "uuid", "updatedAt": "...",
  "payload": {
    "revisions": [
      {"kind": "verify", "interview_client_id": "original-interview-packet", "item_text": "1985年是否已在供销社", "action": "confirm"},
      {"kind": "verify", "interview_client_id": "original-interview-packet", "item_text": "1985年是否已在供销社", "action": "correct", "correction": "修正内容"},
      {"kind": "verify", "interview_client_id": "original-interview-packet", "item_text": "1985年是否已在供销社", "action": "skip"},
      {"kind": "draft", "interview_client_id": "original-interview-packet", "draft": "修订后的初稿全文", "base_version": 1, "revision_reason": "根据家人核对修正年份"},
      {"kind": "person", "name": "三叔", "full_name": "王建军"}
    ]
  }
}
```

- 示例展示可用动作，实际只保留需要的条目，不能对同一核实项同时确认、更正又跳过。
- `action`：`confirm` 确认 / `correct` 修正（填 correction）/ `skip` 转下周追问。
- `kind=draft`：全文修订，必须提供核对过的当前正文 `base_version` 和 `revision_reason`；网站生成新版本并保留旧版。缺少版本、版本过期或原因为空时整包拒绝，请打开故事编辑/历史页核对，不得猜版本或自动增加版本重试。协议外壳 `version` 不是正文版本。
- 正文图片仅允许当前家庭的合法相册引用；不要重写图片 URL。外部/跨家庭/不存在的引用整包拒绝，已删除照片按网页规则显示占位并保留文字。
- `kind=person`：正名（如"三叔→王建军"），旧名记入人物备注。可提供已映射 `person_id` 或 `site_person_id` 明确身份，仅用姓名/别名时必须唯一。

### 7. plan_progress（写作计划进度回写）

```json
{
  "type": "plan_progress", "version": 1, "clientId": "uuid", "updatedAt": "...",
  "payload": {
    "plan_id": null,
    "items": [
      {"person_name": "王建军", "status": "doing"},
      {"person_name": "王德顺", "status": "done"}
    ]
  }
}
```

- 人物匹配：优先使用核对后的稳定 skill 映射；计划 API 返回 ID 时用 `site_person_id`。姓名仅在唯一匹配时回退，同名或别名多候选会整包拒绝。人物不在计划/无法对应时整包拒绝。
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
5. 修订包现在整包原子执行：目标缺失、核实项不明确、版本冲突、无效动作都拒绝并回滚，不能把旧版“部分生效”记录当作整包失败。升级前日志若显示部分生效/跳过，先核对历史，只对确实未生效部分生成新操作，禁止重放已生效修订。
6. **导入失败处理**：把网站返回的错误原文如实告诉用户，不假装成功。失败的数据包不会占用 `clientId`（网站以 failed 记录留痕），**修正数据后用同一个 `clientId` 重新生成整包再导入**，不要每次失败都换新 uuid；若其实已经入库成功，同 `clientId` 重发会被网站自动跳过，不会重复。

## 七、程序接入边界

主路径仍为管理员在浏览器逐包粘贴。skill 没有网站会话，不能声称已直连、已入库，也不向用户索要 Cookie 或密码。

若后续另行授权受控程序接入，`POST /api/sync` 需要有效管理员登录会话，请求体是 `{"family_id":"网站家庭id","packet":{同步包}}`；上面的模板只对应内部 packet。没有独立 API key/Bearer 接入能力。

响应 `ok=true, applied=true` 表示当前包已完成；`applied=false` 表示同 clientId 已处理，不是失败。401 是未登录，403 是无管理员权限，404 是无目标家庭权限，不能解释为没有资料；400 时核对错误并确认本包未生效后再重试。首次调用结果未知时先保留原包及 clientId 核对，不换 UUID 猜测重发。

现有协议不创建亲属结构、不保存完整双历月日、不上传媒体、不写人物小传，也不镜像本地目录。
