# 本地存储目录规范（memoir-organizer）

skill 所有需要落盘的内容，按 `~/workspace/memoir/README.md` 的目录规范存放。完整规范见该文件，这里只记操作要点。

## 目录速查

```
~/workspace/memoir/families/<family-id>/
  tree.json                  家族树 canonical（改前先备份到 tree.history/）
  persons/<person-id>/       人物：profile.md + photos/
  sources/<source-id>/       源文件：original.* + meta.json + transcripts/vN.md
  interviews/<interview-id>/ 整理：draft.vN.md + quotes.json + verification.json + timeline.json + person-links.json + meta.json
  weekly/<week-id>/          周报：digest.md + visible/index.html + revision-list.md + sync.json + final.md
  shares/LATEST              当前分享的 week-id
  manifest.json              每次写操作后追加 {path, op, at}
```

## 操作规则

**适用范围**：本规范仅在 Muse 环境（含本地 workspace）有效。在其他模型 App 里安装本 skill 时，改用对话内交付（Markdown 文档 / sync-json 数据包），由用户自行存档或粘贴到后台。

1. **新家庭**：`cp -r families/_template families/<family-id>`，先写 `family.json`，再跑家族树模式生成 `tree.json`。
2. **命名**：person `p01` 起；source `src-YYYYMMDD-NN`；interview `iv-YYYYMMDD-NN`；week `week-NN`。
3. **版本**：源文件只追加；`tree.json` 改前备份；draft 存新版本不覆盖；每次写完更新 `manifest.json`。
4. **人物 id 一旦分配永不复用**，删除人物用软删（tree.json 里标 status=removed）。
5. **同步**：整目录即云端镜像单元；`tree.json`/`interviews/`/`verification.json`/`weekly/*/sync.json` 分别对应 sync 数据包的四种 type（见 `memoir-sync-design.md`）。

## 周报/定稿落盘位置

- 周报模式输出 → `weekly/<week-id>/digest.md`
- 可见版本 HTML → `weekly/<week-id>/visible/index.html`
- 修订清单 → `weekly/<week-id>/revision-list.md`
- 本周定稿 → `weekly/<week-id>/final.md`
- 修订同步包 → `weekly/<week-id>/sync.json`
