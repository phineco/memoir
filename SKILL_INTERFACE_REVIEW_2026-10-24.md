# memoir-organizer 与当前网站接口兼容性审查

日期：2026-10-24。审查基线：`da3daa1`，本轮开始时工作树干净。

## 结论

七种同步类型及相关 API 路径仍存在，在登录、人物映射和目标数据正确时能够交互；但目前不能认为 skill 已完整适配当前仓库。需要同时修订 skill 文档契约与服务端同步保护，单改提示词不足以解决权限、覆盖和图片丢失问题。

`skill/memoir-organizer/` 当前只有 SKILL.md 和六份 references，共七个 Markdown 文件，没有可执行 HTTP 客户端、凭据管理或结果解析脚本。本次将这些文件作为被审查对象，没有执行其采访、存档或同步指令。

本轮仅审查：未修改 skill、接口或业务实现，未访问生产资料、发起线上写入或调用付费服务。

## 验证范围

- 完整阅读七份 skill 文件，对照 `views.py`、`sync_engine.py`、人物映射、故事权限、图片清洗和核实状态模型。
- 用临时 SQLite 与合成用户执行 12 项行为探针，以及 61 项现有同步、家庭隔离、生存状态和日期回归，共 73 项通过。
- 探针断言的是“当前问题能够复现”，通过不代表这些行为符合产品要求，更不能代替修复后的验收测试。
- 用本机 Ruby/Psych 的标准 YAML 解析器验证 frontmatter，得到语法错误。未验证不同宿主安装器的实际加载行为。
- 未执行真实 MySQL、真实外部模型或真实生产接口联调。

临时复现目录：`/private/tmp/memoir-skill-audit-st4sjmq4`；脚本 `tests/test_skill_interface_audit.py`，观测值 `skill-audit-results.json`。这些探针未加入应用测试集，修复时应改写为期待正确行为的回归用例。

## 一、需要优先修复的问题

### P0：同步修订绕过当前文章权限

证据：[同步修订](/Users/louisw/github/memoir/sync_engine.py:335)、[核实更新](/Users/louisw/github/memoir/sync_engine.py:249)、[网页编辑权限](/Users/louisw/github/memoir/views.py:846)。

`POST /api/sync` 检查家庭管理员资格，后续 `revision_sync` / `verification_update` 只检查目标属于本家庭，没有复用文章的可见性、作者及整理权限。

已复现：

1. 建立由普通成员创作的私密故事。
2. 家庭创建者读取故事和打开网页编辑页均返回 404。
3. 同一创建者向同步接口提交该故事的修订，返回 `ok=true` 并创建版本 2；核实更新也能修改这个无权阅读故事的核实项。

影响：当前明确禁止的管理员越权修改，可从同步入口发生。此验证证明了写入越权，没有证明私密正文可被该接口读出。

修复方向：两个入口使用同一文章权限服务；已有故事修订和核实处理均校验目标文章的实际权限。管理员身份不能代替文章授权。修复前，私密和非本人内容应使用现有网页授权流程处理。

### P1：SKILL.md frontmatter 无法被标准 YAML 解析

证据：[SKILL.md 第 3 行](/Users/louisw/github/memoir/skill/memoir-organizer/SKILL.md:3)。

`description` 结尾多一个双引号。Ruby/Psych 解析返回 `Psych::SyntaxError: did not find expected key`。

影响：按 YAML 读取元数据的宿主可能无法加载 skill，尚未进入接口交互就失败。此处是语法问题，实际宿主是否另有容错尚未验证。

修复方向：纠正 frontmatter，并增加装载格式检查。

### P1：“初稿入库”实际上直接全家可见发布

证据：[导入创建故事](/Users/louisw/github/memoir/sync_engine.py:165)、[skill 初稿包模板](/Users/louisw/github/memoir/skill/memoir-organizer/references/sync-guide.md:75)。

`interview_upsert` 固定设置 `publish_status='published'`，可见性使用模型默认的 `public`，这里的 public 表示家庭内可见。skill 的模板只说同步初稿，没有明确告知这是立即发布给全家。

已复现：即便额外传入 `publish_status='draft'`、`visibility='private'`，服务器也会忽略，落库为 `published/public`，另一普通家庭成员可以阅读。

这些字段目前并非已支持的同步参数，不能靠 skill 添加字段实现隐私控制。导入后的内容也可能成为周报和家庭 AI 知识库来源。

修复方向：明确“保存”和“发布”的区别，增加服务端可验证的发布/可见性契约及确认；未支持的隐私字段应拒绝或明确报错，不能产生相反效果。同步同意不能默认等于全家发布同意。

### P1：同步全文修订没有版本冲突保护

证据：[同步全文修订](/Users/louisw/github/memoir/sync_engine.py:335)、[网页修订保护](/Users/louisw/github/memoir/views.py:1306)。

网页会检查 `base_version`、修订原因和并发变化；同步修订直接取当前正文，再新增下一版本，没有版本前置条件和同等并发保护。

已复现：先写版本 2，再发送依据版本 1 的旧全文，仍成功创建版本 3 并替换当前正文。附带自定义 `base_version=1` 不起作用。外壳 `version=999`、旧 `updatedAt` 也被接受，二者目前不提供正文冲突控制。

注意：协议版本 `version` 与文章版本 `base_version` 是两回事，不应互相代替。

修复方向：定义并校验文章基础版本，复用原子修订逻辑；旧版本拒绝后提供核对路径。保留修订原因及来源记录。协议版本另外验证，并明确旧 v1/缺省版本的兼容规则。

### P1：同步修订会移除已有相册图片

证据：[同步清洗函数](/Users/louisw/github/memoir/sync_engine.py:27)、[允许家庭图片的清洗分支](/Users/louisw/github/memoir/sanitize.py:28)。

同步调用不带家庭上下文的通用清洗器，默认不允许 `img`；网站编辑器已支持家庭相册内图。

已复现：把包含合法本站相册图片的原正文原样提交 `revision_sync`，新版本的图片从 1 张变为 0 张，文字仍保留，接口没有提示图片移除。

修复方向：与网页编辑共用家庭图片校验和清洗规则。这里的问题是修订已有文章会丢图，不是要求 skill 承担照片上传或原图归档功能。

### P1：核实状态 `corrected` 与网站状态不一致

证据：[skill 核实状态](/Users/louisw/github/memoir/skill/memoir-organizer/references/sync-guide.md:119)、[后端转换](/Users/louisw/github/memoir/sync_engine.py:264)、[正文状态显示](/Users/louisw/github/memoir/templates/story.html:44)。

skill 允许 `verified/corrected`。服务器只把 `verified/resolved` 转成 `resolved`，将 `corrected` 原样保存；网站模型、显示和指标以 `resolved` 表示已解决。

已复现：发送 `corrected` 后 HTTP 成功，但状态仍是 `corrected`、`resolved_at` 为空，故事页继续显示等待图标。`revision_sync` 的 `action=correct` 却会存成 `resolved`，两条路径不一致。

修复方向：统一状态语义、校验枚举与更正内容。已有 corrected 数据应核对兼容；不能给历史记录伪造实际核实时间。模型对真正进入 resolved 的新变更已有时间记录钩子，不应误判为整个系统都缺少该能力。

### P1：人物 ID 命名空间不一致，同名消歧不足

证据：[人物解析](/Users/louisw/github/memoir/sync_engine.py:33)、[故事人物解析](/Users/louisw/github/memoir/sync_engine.py:148)、[计划回写](/Users/louisw/github/memoir/sync_engine.py:395)、[skill 计划指南](/Users/louisw/github/memoir/skill/memoir-organizer/references/writing-plan-guide.md:12)。

`GET /api/writing-plan` 返回网站人物 ID；同步的 `person_id` 等字段却被当成外部 skill ID 去查映射，不会直接按本站 Person.id 对应。文档示例把返回人物 ID 也写成 p01，掩盖了两者区别。

已复现：直接回写计划 API 返回的真实人物 ID，结果为“更新 0 人”，但 `ok/applied` 均为 true；把该 ID 用作故事主角/讲述者且无名称回退时，两者都为空。

进一步差异：讲述者可用 `narrator_name` 回退，主角和关联人物当前只传外部 ID 查映射，不能把所有字段都概括成“姓名匹配能兜底”。

同名问题也已复现：两个同名人物存在时，tree_upsert 仍选第一个并建立映射，不报告歧义；别名匹配同样返回首个候选。“优先用姓名最稳”应纠正。

修复方向：明确区分本站 ID 与 skill ID，建立可核验映射；计划回写优先使用明确身份，姓名/别名多候选时拒绝自动绑定。返回机器可读的未匹配/冲突项，而不只用成功状态加文字摘要。

### P1：鉴权和 HTTP 请求契约没有写清

证据：[skill 声称开放](/Users/louisw/github/memoir/skill/memoir-organizer/references/writing-plan-guide.md:8)、[写作计划 API](/Users/louisw/github/memoir/views.py:2616)、[同步 API](/Users/louisw/github/memoir/views.py:2124)。

隔离结果：

| 请求 | 当前行为 |
|---|---|
| 未登录读取计划 | 401 |
| 只传一个 Bearer 字符串、没有登录会话 | 401 |
| 当前家庭普通成员读取计划 | 200 |
| 普通成员调用同步写入 | 403 |
| 将 skill 根数据包直接 POST，未传 family_id | 404 |

API 需要网站登录会话；没有独立 API key/MCP 服务。程序写入常用外壳为 `{"family_id":"...","packet":{...}}`，服务端也兼容 family_id 与 type 同层的格式。skill 模板只是内部 packet，不是完整 HTTP 请求体。

修复方向：删除“开放接口”表述，写清管理员/成员区别、会话、请求外壳和响应处理。401/403/404 不能当作“没有计划”，也不能把当前接口改成公开来绕过登录。近期可继续由用户提供计划，管理员在浏览器导入；真正自动化连接另做受限授权。

## 二、次优先修正与能力边界

### P2：多个同步包粘贴时只处理第一个

证据：[粘贴解析](/Users/louisw/github/memoir/views.py:2092)。

skill 要求初稿、人物状态和计划进度在同步节点一起输出，但没有说明当前网页一次只接受一个包。页面用首个匹配提取 sync-json 代码块。

已复现：一次粘贴两个有效代码块，只入库第一个；数组批量不是当前支持的格式。

应明确“每包分别导入”，或另行建设批量预览与逐项结果。`ok=true/applied=true` 不代表所有代码块或所有人物都生效；同一包重试保持 clientId，新操作生成新 UUID。

### P2：建树的前后闭环不完整

同步指南一处说新人物加入下一次 tree_upsert 即可，另一处又正确说明“不自动入树”。当前实现只把未匹配人物登记为 NewPerson，不创建真实人物、不建立其映射，也不修改亲属结构。

已复现：新人物 tree_upsert 成功后仅有 pending 候选，Person 和 PersonIdMap 均未新增。

应明确流程：管理员在家人页添加/核对人物 → 以新的同步包为稳定外部 ID 建立映射 → 再导入关联故事或进度。当前 seven-type 协议没有亲属结构创建、完整双历日期、照片/音频文件上传或人物小传写入能力，不能把“整树/整目录镜像”当成这些功能已经实现。

已有年份更新会保护精细双历日期，冲突时整包拒绝；该保护仍有效，不应为适配 skill 而删掉。完整公历/农历信息目前通过人物表单核对。

### P2：参考文档与本地存储说明需更新

- sync-guide 的 type 枚举只有六项，漏列实际支持且正文已写出的 plan_progress。
- storage-guide 仍称“四种 type/整目录云端镜像”，与当前七类 JSON 入库及独立私有媒体存储不符；本地 photos、原录音、manifest 不会因此上传网站。
- 当前机器的 `~/workspace/memoir/README.md`、`families/_template` 不存在；skill 单独打包目录内也没有被引用的根协议文件。仅在 Muse 使用的存档模式需补齐模板；其他环境按其原有边界使用对话交付，不应创建这些路径冒充已有规范。
- 周报路径使用 week-NN，缺年份，与网站 ISO 年周口径不一致；跨年有复用目录风险。
- 家族树示例把“三叔、姑姑”画成父亲的子女，应纠正到同辈分支。
- 导入引导位置仍写“家族树管理区”；当前入口为家人 → 家庭管理 → 资料工具 → 同步入库。
- version、updatedAt、treeId、generation、narrator_relation 等字段不能据其出现在示例里，就推定已被服务器验证或完整保存。
- skill 周报当前按对话/用户粘贴材料汇总；网站周报已按首次发布时间、ISO 年周和可见性聚合。要接通站内核实，应保留周报编号到原导入 clientId/核实项 ID 的对应表，不能只靠编号或改写后的片段猜目标。

## 三、确认仍然兼容的部分

- 七种 type 都有处理器，且在正确前提下分别成功完成：tree_upsert、interview_upsert、verification_update、new_person、person_status、revision_sync、plan_progress。
- API 与网页入口仍存在，本次导航重组没有删除这些接口。
- 同一 clientId 成功后幂等跳过；失败包可以修正后重试，现有失败日志与跨家庭目标防护回归通过。
- 已有明确人物可通过 tree_upsert 的全名/映射完成对应；新人物不会被擅自挂进关系树。
- YYYY / YYYY-MM / YYYY-MM-DD 的标准时间轴格式能够解析精度。
- 新导入故事记录账号作为作者，讲述者另存，符合当前“陪家人记录”的身份口径。
- 模型钩子会为真正进入 resolved 状态的新变更记录核实时间；问题在 corrected 路径没有统一状态。

## 四、建议开发顺序

1. 先修同步写入的文章权限，补本人/其他作者、私密/指定人、跨家庭及普通成员回归。
2. 统一保存/发布与可见性、版本前置条件和家庭图片处理，避免错误发布、覆盖和丢图。
3. 对齐人物 ID 与同名消歧、核实状态及结构化结果，补技能示例到实际服务端的契约测试。
4. 修正 frontmatter、鉴权/请求封装、单包导入、建树操作与当前入口文案；明确未交付的媒体镜像等能力。
5. 独立评估批量同步和安全自动接入。不要用普通会话口头确认替代服务端权限及冲突校验。

本轮为审查结论，不代表上述修复已经完成；未对生产接口进行验证。
