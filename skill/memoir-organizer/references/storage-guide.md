# 本地存档规范（memoir-organizer）

仅在 Muse 有可写 workspace 且用户要求落盘时使用。其他 App 使用对话内 Markdown / sync-json 交付，由用户保存。不依赖包外 README、预装模板或云端目录。

## 位置与最小结构

使用用户指定的存档目录；已有 `~/workspace/memoir/` 时可继续沿用。目录不存在或不可写时先确认可用位置，不复制不存在的模板，不假装已保存。

```text
<archive-root>/families/<website-family-id>/
  family.json                 网站家庭 ID 与用户确认的名称
  tree.json                   本地人物及关系资料，不等于网站已有映射
  tree.history/               修改前备份
  persons/<skill-person-id>/  profile.md 与用户提供的照片
  sources/<source-id>/        原始资料、meta.json、transcripts/vN.md
  interviews/<interview-id>/  draft.vN.md、quotes.json、verification.json、timeline.json、meta.json
  weekly/<iso-year>-W<week>/  digest.md、revision-list.md、final.md、sync.json
  manifest.json               本地写入与手动导入的记录
```

首次保存最少建立 family.json、本次内容所在目录和 manifest.json；其余按实际需要建立，不生成空文件冒充已有资料。家庭 ID 使用网站真实标识，不能另编“家庭代号”代替。

## 命名、版本与同步

- 本地人物使用稳定 skill ID（如 p01），记录核对后的网站 ID 映射；旧 ID 永不换人。人物归档或移除是本地标记，不把 removed 发送为网站采访状态，也不声称网站人物已删除。
- source 可用 src-YYYYMMDD-NN，interview 可用 iv-YYYYMMDD-NN；周报用 ISO 周所属年份，如 2026-W43，不能只有周数，跨年不混目录。
- 原始资料只追加；修改树前保存历史，初稿每次保存新版本，不覆盖用户原文件。首次从旧 week-NN 目录继续时先核对年份，不凭当前年份移动历史资料。
- manifest 使用 JSON 数组记录 {path, op, at}；有同步包时另记其 clientId、type、状态 pending/confirmed/failed。用户反馈网站成功前，只能记待导入；反馈未知时保留原包核对，不猜成功，也不换 UUID 重发。
- 本地目录是个人存档，不是云端镜像。网站只接收 sync-guide 中七类 JSON，照片、原始录音、manifest、亲属结构不会随包上传。不要把本地 visible/index.html 或 shares/LATEST 当作已发布分享链接。
- 周报编号到原稿/故事/核实项的对应表与 revision-list 一起保存，供后续核对修订。
