# sync-json 同步协议

更新日期：2026-10-20，以 `sync_engine.py` 为执行实现。外部采访助手不随本仓库交付。

## 一、入口与包格式

家庭管理员在 `/f/<family_id>/sync` 粘贴 JSON 或 `sync-json` Markdown 代码块。程序调用 `POST /api/sync` 须携带已登录管理员会话，没有独立 API key 或 MCP 服务。

```json
{
  "family_id": "family-id",
  "packet": {
    "type": "interview_upsert",
    "clientId": "globally-unique-packet-id",
    "payload": {"topic": "童年的河", "draft": "<p>故事初稿。</p>"}
  }
}
```

`clientId` 为协议字段，数据库字段为 `client_id`，不能混用。建议 UUID hex（32 字符）；同一包重试保持不变，新修订生成新 id。现有唯一约束为全站范围，不同家庭也不能复用。

## 二、人物对应

先查本家庭外部 `skill_id → person_id` 映射，再全名精确匹配，最后匹配别名。外部 id 与网站 id 不天然相同，通过 `tree_upsert` 建立映射。对应不上则记为待定或留空，不猜测挂靠。

`tree_upsert` 不新增树节点、不改挂靠；新人物由管理员确认后手动入树。同名或同别名可能有歧义，须人工消歧。

## 三、七类数据包

下列字段放入 `payload`：

| type | 字段与行为 |
|---|---|
| `tree_upsert` | `persons: [{id, fullName, aliases, birthYear, deathYear, alive, status, relation, notes}]`；更新已有资料与映射，对不上则记待定人物 |
| `interview_upsert` | `topic, draft, subject_person_id, narrator_person_id, narrator_name, period_start, period_end, period_precision, quotes, verification_items, timeline, related_persons`；新建已发布故事及相关资料 |
| `verification_update` | `interview_id` 或 `interview_client_id`；`item_id` 或 `item_text`；`status, correction`；修改本家庭故事的核实项 |
| `new_person` | `name` 必需，`context` 可选；记录待定人物，不自动入树 |
| `person_status` | 外部 `person_id` 或 `name`，以及 `status`；更新人物采访状态 |
| `revision_sync` | `revisions: [...]`；核实、全文或正名修订，详见下一节 |
| `plan_progress` | 可选 `plan_id`（不填取当前 active 计划），`items: [{person_id, person_name, status}]`；更新已在计划中的人物，进度支持 `pending/doing/done` |

人物采访状态约定 `pending/doing/drafted/verified`。`interview_upsert` 实际按包新建：相同包跳过，不同包会新建故事；修改旧故事用修订包。

附属字段示例：

```json
{
  "quotes": ["长辈的原话"],
  "verification_items": [{"text": "年份待确认", "reason": "两次口述不一致"}],
  "timeline": [{"date": "1978-05", "event": "搬入新家"}],
  "related_persons": [{"person_id": "external-person-id", "role": "related"}]
}
```

故事起止日期为 `YYYY-MM-DD`，`period_precision` 为 `year/month/day`。时间轴日期接受 `YYYY`、`YYYY-MM`、`YYYY-MM-DD` 并保留精度。讲述者未对应时保存名字到备注，不强行绑定。

## 四、修订与读取计划

`revision_sync.payload.revisions` 支持：

```json
[
  {"kind": "verify", "interview_id": "site-story-id", "item_id": "verification-id", "action": "correct", "correction": "应为1979年"},
  {"kind": "draft", "interview_client_id": "original-import-packet-id", "draft": "<p>修订后的全文。</p>"},
  {"kind": "person", "name": "旧名", "full_name": "正确姓名"}
]
```

核实动作：`confirm` 确认，`correct` 修正，`skip` 保持待核实并记为下周追问。全文修订保留旧版本，正名把旧名记入备注。`interview_client_id` 指最初故事入库包的 `clientId`，只允许引用当前家庭故事。

带家庭成员会话调用 `GET /api/writing-plan?family_id=<id>` 读取当前计划，调用 `GET /api/weekly-report?family_id=<id>&week=<week>` 读取周报。周报 API 仅导出家庭内 public 已发布故事，不导出私有或指定人故事。

## 五、结果、幂等与事务

- 成功：`{"ok": true, "applied": true, "summary": "..."}`。
- 重复包：`ok=true, applied=false`，不再次写入。
- 协议或跨家庭目标错误：HTTP 400；未登录 401，管理员不足 403，无家庭权限 404。
- 修改在事务内执行，失败回滚；可识别的同步错误记入失败日志，修正后可复用原 `clientId`。
- 当前仅有基础结构校验，不是完整 JSON Schema 校验，异常嵌套字段仍可能报服务器错误。
- `sync_log` 记录结果；管理员应阅读摘要核对，不把 HTTP 成功视为所有条目都已对应。
