# ontokb — 稍后观看研究管线 + 知识图谱

## 人工整理实体与关系

点击顶部「整理知识」，搜索实体、论断或关系；也可以从图谱节点和关系证据直接进入编辑。实体支持修改名称、类型和别名，论断可记录人工核验状态；关系支持修改两端实体、关系类型与抽取置信度，或移除错误关系。出处和原始证据保留为只读。桌面菜单「阅读 → 整理知识」的快捷键为 `Ctrl+Shift+E`。

知识漫游不依赖右键：普通点击节点后，可用信息区的“⋯”打开操作菜单；点击关系连线或证据行的“⋯”也可编辑关系。多来源连线先选择具体资料，再编辑对应记录。打开菜单会暂停漫游；右键和 `Shift+F10` 保留为快捷入口。编辑器详情中可独立保存个人审核、记忆范围、个人立场及判断说明，并按记忆范围和审核状态筛选列表。知识内容与个人记忆分别保存，避免把修正抽取内容当作认可观点。

保存会校验正式名称冲突和本体约束，同步相关 Obsidian 笔记并刷新图谱。别名允许重名：同一别名可以属于多个实体，搜索返回候选；抽取仅遇到歧义别名时会拒绝自动归并，需使用正式名称或人工确认。改名保留旧名称以维持资料匹配；人工修改及移除决定会被记录，重新分析同一来源时受到保护。编辑器提供最近修改记录和撤销入口，存在更新冲突时会要求重新加载。SQLite 仍是数据源，不需要安装其他数据库工具。

已有两个记录实际代表同一实体时，点击编辑器顶部「合并实体」或详情中的「合并到已有实体」。选择要归并的记录与保留实体，预览别名、关系、出处和个人判断影响；确认后，保留实体的正式名称和编号，另一名称成为别名。重复关系的各份原始证据仍可在关系详情及图谱查询中查看。个人判断原快照保留并关联到统一实体，不自动把旧认可转移到改变后的论断／关系。资料文档与类型不同的记录不能直接合并。

合并记录可从保存反馈或修改历史中撤销，恢复原实体、关系、别名与笔记。撤销会检查知识、个人判断和笔记是否已发生其他变化；若发生变化则拒绝覆盖。合并后重新抽取会复用统一身份，并保留人工关系修正及移除决定。

后端接口：`GET /api/editor`；`POST /api/editor/entities/{id}`、`POST /api/editor/triples/{id}`、`POST /api/editor/triples/{id}/delete`、`POST /api/editor/changes/{id}/undo`。更新时提交读取到的 `revision` 可检测过期编辑。更新代码后需重启后端并刷新页面。

合并接口：`POST /api/editor/entities/{id}/merge-preview`，请求 `{target_id}`；`POST /api/editor/entities/{id}/merge`，请求 `{target_id, preview_token}`。预览之后数据变化会使令牌失效，必须重新预览。旧别名索引会自动迁移为允许多个实体共享的结构。

## 个人记忆与判断变化

页面顶部“个人记忆”可对实体、论断及每条带来源的关系分别设置：未审核／已审核、仅资料库／纳入个人记忆。论断和关系还可记录未表态／认同／存疑／不认同，以及个人判断和适用条件。审核、记忆范围、个人立场与现有事实核实状态相互独立；旧数据默认未审核、未纳入，不自动把已核实或人工编辑理解成个人认可。标记实体不会自动标记它的全部关系。

先从其他资料中保存个人判断，再选一篇新资料，点击“新资料对旧判断的影响”。系统通过现有模型对照已审核、已纳入且有个人立场的论断／关系快照与新资料的摘要、抽取关系和证据，给出待确认建议。不会自动修改立场；保存判断时可选择影响资料，并在“判断变化记录”查看前后立场、说明与时间。快照用于保留当时判断，不能证明判断早于所选资料入库；同来源判断不作为对照基线。

元数据与历史保存在 SQLite 独立表中，当前不投影到 Obsidian，也不改变普通 Chat 的检索范围。原论断内容或关系证据改变后，新记录不继承旧标记；旧判断仍以历史快照保留。第一版比较最多 150 条旧判断、120,000 字符上下文，超限明确报错，不静默省略；对照是模型建议，不是自动事实核查或完整全文分析。

接口：`GET /api/memory`；`POST /api/memory/review`（key、revision、reviewed、included、stance、note、可选 source_id）；`POST /api/memory/compare`（source_id）。重启 API 后刷新页面即可使用。

## 阅读工作台与摘要漫游

### 多媒体漫游：视频精剪与较长原声回顾

选择已入库的 YouTube 资料，点击摘要上方「视频精剪」或「原声漫游」，可选择两种节奏。视频精剪以约 90 秒为目标、最长 2 分钟，将精选画面与原声拼成可播放和下载的 MP4。原声漫游以原视频长度的三分之一为目标，保留更多讲述上下文，以截图配原声播放，并可下载合并音频。例如约 9 分半的视频，原声版目标约 3 分 10 秒。两种模式都保持原语速；截图在对应原声结束后切换，不通过慢放来延长时长。

系统把现有摘要与带时间戳的字幕进行匹配，保留原视频的先后顺序和来源时间链接。实际长度按可用字幕片段调整；资料较短或可靠片段不足时，不强行填满目标时长。字幕保留原声的具体讲述，摘要表达对应的要点；支持暂停、前后切换、重播，以及原声漫游和视频成片的进度拖动。原声进度条覆盖整个漫游，可跨片段定位，并同步截图、字幕与摘要。

原声漫游和视频精剪共用阅读工作台右侧的播放器，左侧保留同一份摘要，并同步高亮当前讲述对应的段落。点击有原声对应的摘要段落，可跳转到该段原声或成片时间点；没有选入本次剪辑的段落会明确提示，不跳到无关内容。右侧按原字幕时间轴逐句显示中文字幕；外语字幕通过 Codex 翻译，已有中文字幕保留原文，声音保持原视频语言和语速。字幕和摘要由原始时间戳及受校验的段落索引关联，不把整篇摘要误当成逐字字幕。关闭播放器可返回图谱。

图谱控制条的「定位本段原声」可跳到当前摘要对应的原声片段；返回图谱会保留媒体漫游最近关联的摘要位置。未收录的段落会明确提示，切换资料不会沿用上一篇的定位。没有字幕的时间段留白。

原声漫游截图区域下方的横向分隔条可上下拖动，调整截图与字幕区域的高度，并记住设置；也可聚焦分隔条后用上下方向键调整。

已生成的视频、原声音频和截图会复用，补充字幕与摘要对应数据；首次补充可能需要几分钟。优先生成中文译文，也允许英文或中英混合字幕正常播放，不因缺少中文字符阻断漫游。模型返回使用结构化格式约束；通过校验的字幕逐句缓存，只补空缺或无效的句子，批次连续失败会自动拆小后重试。文本必须非空，字幕编号与摘要索引仍严格校验；不会为不相关的字幕强行指定摘要段落。已有字幕缓存继续复用。

安装 `python -m pip install -e ".[media]"`（本机本次已补齐 FFmpeg 依赖），并确保本机 Codex CLI 已登录。如视频没有可用字幕，还需 `[youtube]` 中的本地 Whisper。两个生成入口均通过 `codex app-server` harness 执行：Codex 读取项目内 npocut skill，依次调用受限的检查、生成、验证工具；本地媒体管线负责执行。原声音色和语言来自视频，不生成配音或翻译音轨。Codex 不可用时明确报错，已完成的媒体播放可直接复用缓存。

首次生成会下载视频、补取旧文字稿缺失的时间轴、生成截图与剪辑，可能需要数分钟；关闭播放器不会中断后台生成。结果缓存在数据库旁的 `media/` 中，两种模式分别缓存、共用下载的原视频；摘要改变后重新生成。字幕获取、下载和转码都有超时，视频访问受限时显示可重试提示。纯文字文章暂不支持原声模式，仍可使用原有图谱漫游。

接口：`POST /api/media/prepare`（`content_id`、`mode`）、`GET /api/media/status?content_id=…&mode=…`、`GET /api/media/asset?content_id=…&mode=…&name=…`。`mode` 为 `video` 或 `audio`，默认 `video`；媒体接口支持 Range 播放与成品下载。更新后重启后端并刷新页面。

[npocut](https://github.com/roclive/npocut) 的完整源码、正式 `SKILL.md` 和 MIT 许可证已放入 `third_party/npocut`，固定版本见 [来源说明](third_party/NPOCUT.md)。两个工作流先保存 `clip_plan.csv`，实际调用 npocut 的 `srt_slice.py` 重排字幕时间轴，并保留中文 SRT。剪辑计划、SRT 和媒体均留在忽略的本地缓存目录；可在生成清单中查看 skill 版本及 harness 工具执行记录。

首页已重做为左侧资料摘要、右侧动态知识图谱。点击摘要段落或“开始漫游”，镜头会聚焦对应实体与当前资料已记录的关系；支持暂停、前后导航、播放速度、证据查看、类型筛选和减少动画设置。

点击“新建摘要”粘贴文章标题、正文及可选来源链接，即可生成摘要与要点，按本体抽取实体关系并保存到 SQLite/Obsidian。文章原文保存在内容元数据中；重复提交相同标题、链接和正文会复用。使用现有模型配置，需要模型可用。当前入口处理粘贴正文，不自动抓取任意文章 URL。

`GET /api/reading` 返回资料摘要、漫游步骤和图谱；`POST /api/articles` 接受 `{title, text, url}`。漫游按名称／别名匹配，不把摘要共现当成新关系；无匹配段落显示提示。Electron 0.2.0 共用相同页面，并提供 Ctrl+N 新建文章摘要。

## Schema.org 本体重构（2026-09-26）

当前采用 `ontology/core.yaml` 中的 Schema.org 受控应用剖面 v2：人物、组织、软件、概念术语、视频、文章、书籍和论断有明确分类边界。旧 `Topic/Technology` 兼容映射为 `DefinedTerm`，视频使用 `VideoObject`，旧 `worksAt` 规范为 `worksFor`。本地扩展关系使用独立 URN，不能当成 Schema.org 官方属性。

本机现有数据已备份并完成迁移：63 个节点、90 条关系保留，23 个节点类型调整，River 标为待复核。页面提供实体／概念、论断、资料及全部视图，图例与类型均可筛选。完整选型、优缺点、迁移结果和限制见 [本体分析报告](docs/ontology-analysis.zh-CN.md)。

```powershell
python -m ontokb.cli migrate-ontology --report data/ontology-review.json  # 只预检
python -m ontokb.cli migrate-ontology --apply  # 其他旧库：备份后迁移；本机无需重复
python -m ontokb.cli export-jsonld --out data/knowledge-graph.jsonld
```

迁移记录包含数据库及 vault 备份路径。结构校验不等于事实核查；论断仍保留出处并标记未验证。下文旧架构中的 Content/Topic/worksAt 对应上述兼容名称。

## 本机 Codex 入口（新增）

默认配置已改为 `llm.provider: codex`、`model: null`，使用本机 Codex 登录与模型设置。问答与结构化抽取都通过 `codex app-server` 执行。已有 `config/config.yaml` 需同步这两个字段。API 模式仍可选择 openai/anthropic。

Windows 在仓库目录运行：

```powershell
python -m pip install -e ".[dev,html]"
codex login
.\start.ps1
```

浏览器打开 <http://127.0.0.1:8765>，无需使用下方旧版 macOS 文件路径。刷新页面即读取当前图谱。跨平台也可运行 `python -m ontokb.cli api`。

Chat 支持直接发送 YouTube 链接，例如“分析 https://www.youtube.com/watch?v=XAujxrtd4uI 并入库”。系统自动获取字幕，无字幕时下载音频并用本地 Whisper 转写，再由 Codex 提取摘要和关系，保存到 SQLite / Obsidian 并回答。页面显示阶段进度；已入库视频复用已有分析。刷新页面可查看新增图谱。需安装 `python -m pip install -e ".[youtube]"`；首次无字幕视频会下载转写模型，长视频可能耗时较久。

当前每条消息处理第一个有效 YouTube 链接；其他消息查询知识库。Chat 会向模型传入最近 10 轮完整对话（最多 32,000 字符，超限淘汰最旧轮次），视频追问会继续携带最近已入库视频的正文。点击“新对话”或刷新页面清空历史；暂不跨重启保存，也不支持 token 流式展示和工具审批。每次 Codex 调用超时 180 秒，下载/转写耗时另计。CLI 存在性检查不代表登录仍有效，可运行 `codex login status` 验证。

日常建议：每天用 `python -m ontokb.cli ingest "URL"` 收录一两条 YouTube/网易资料，围绕明确实体查询证据，在 Obsidian 打开本仓库 `vault` 阅读摘要；每周运行 `python -m ontokb.cli rules` 整理主题。YouTube 需另装 yt-dlp，无字幕转写还需 faster-whisper。`queue` 仅入队，尚不自动消费；自动报告尚未完成。下一步优先补粘贴文本/URL 收件箱、后台入库队列和每周回顾。

Codex 模式不要求另填 OPENAI_API_KEY；以下关于 API Key 的说明仅适用于 API provider。协议参考：[Codex App Server](https://learn.chatgpt.com/docs/app-server)。

把 **tech.163.com** 文章和 **YouTube 稍后观看**清单接入一条自动化管线:抓取全文/字幕转录 → LLM 生成摘要、重点、主题相关度 → 按 **ontology** 抽取实体关系写入**知识图谱** → **规则引擎**驱动自动整理(wiki 页、MOC、报告队列)→ 全部落入 **Obsidian vault**。

本仓库同时是 **Fable 5 vs GPT-5.5** coding 能力对比测试的载体,见 [docs/PRD.md](docs/PRD.md) 与 [docs/scorecard.md](docs/scorecard.md)。

## 架构

```
watch list / URLs ──► sources/ (yt-dlp 字幕 · 163 正文抽取)
                          │ raw_text
                          ▼
                      llm.py (OpenAI/ChatGPT structured output)
                          │ summary · key_points · relevance · entities · triples
                          ▼
        ontology/core.yaml ──校验──► graph.py (SQLite 三元组库, 别名归并, 源标记)
                          │ + 文档层: 每条内容一个 Content 节点
                          │   (about/mentions 边由 pipeline 确定性生成)
                          │ facts
                          ▼
                      rules.py (前向链式规则引擎, rules/default.yaml)
                          │ actions
                          ▼
                      vault.py ──► Obsidian vault (Sources/Entities/Wiki/MOC/Reports)
```

## 图谱建模：文档-实体双层图

所有信息源（YouTube / 网易 / …）写入**同一张图**（统一 Schema），跨媒介的同一实体自动归并，
同时通过源标记保持逻辑隔离与可溯源：

- **文档层**：每条被 ingest 的内容由 pipeline 确定性地创建一个 `Content` 节点
  （属性含 `url`、`source`、`kind`、`added_time`、`published_at`，并以 content id 为别名），
  不依赖 LLM 输出；再自动生成 `Content --about--> Topic` 与 `Content --mentions--> 实体` 边。
- **知识层**：LLM 只负责抽取实体之间的关系（`worksAt` / `develops` / `makesClaim` / …），
  并按 prompt 做实体对齐——"GPT母公司"这类间接指称会解析到 `OpenAI` 并记入 aliases。
- **源标记**：实体行累积 `sources`（提到过它的全部 content id）与 `added_time`（首次入库时间）；
  每条三元组带 `source`（出处 content id）与 `created_at`。
  查询任意实体即可顺着 `mentions` 边或 `sources` 字段回溯到原始视频/文章链接。

## 快速开始

```bash
pip install -e ".[dev,llm,youtube,html]"
cp config/config.example.yaml config/config.yaml   # 填 interests 和数据源
pytest                                             # 40 个单测,无网络依赖

ontokb ingest "https://www.youtube.com/watch?v=..."   # 单条端到端
ontokb queue                                          # 批量入队
ontokb rules                                          # 跑规则引擎
ontokb status
ontokb visualize                                      # 重新生成 vault/Knowledge Graph.html 交互图谱
ontokb api                                            # 启动 SQLite graph 查询 API
```

默认使用 OpenAI/ChatGPT,需要 `OPENAI_API_KEY`。模型默认 `gpt-5.5`,可用 `ONTOKB_MODEL` 覆盖。
YouTube 字幕或本地 Whisper 转写会缓存到 `data/transcripts/youtube/`,后续同一视频优先复用缓存。

## 启动前端 UI

前端是生成在 vault 中的单文件页面。先启动后端（查询与 Chat 共用这个服务）：

```bash
cd /Users/zhangdapeng/Desktop/obsidianKB/obsidianprojFable
export OPENAI_API_KEY="你的 API Key"
ontokb api --host 127.0.0.1 --port 8765
```

再开一个终端，用 macOS 的 `open` 命令启动前端：

```bash
open "file:///Users/zhangdapeng/Desktop/obsidianKB/obsidianprojFable/vault/Knowledge%20Graph.html"
```

右侧“查询”用于直接查看实体和一跳关系；“Chat”会调用 `POST /api/chat`。查询和 Chat 都可选择按词/全文匹配、是否扩展相关词以及 `Top K`（1–200）；Chat 只会把该策略命中的有限 KG 上下文交给 LLM。API Key 只保留在后端环境中。左右区域之间的分隔线可拖动调整比例，双击可恢复默认宽度。图谱数据更新后，运行 `ontokb visualize` 重新生成此 HTML。

## Graph 查询 API

项目内置一个轻量 HTTP API,直接复用 `graph.py` 的 SQLite 三元组库和别名解析逻辑。Obsidian 当前只消费生成的 Markdown 和 `Knowledge Graph.html`,不提供这里需要的三元组查询接口。

```bash
ontokb api --host 127.0.0.1 --port 8765
```

查询实体及其一跳关系:

```bash
curl "http://127.0.0.1:8765/api/graph/query?q=harness%20agent&mode=phrase&expand=1"
```

如果需要类似终端表格的输出:

```bash
curl "http://127.0.0.1:8765/api/graph/query?q=harness%20agent&mode=phrase&expand=1&format=table"
```

返回文本示例:

```text
相关关系如下：
triple_id	关系
72	Codex -- uses -> harness agent
```

可用接口:

- `GET /health`
- `GET /api/entities/search?q=<关键词>&mode=terms|phrase&expand=0|1&limit=50`
- `GET /api/graph/query?q=<关键词>&mode=terms|phrase&expand=0|1&limit=50&format=json|table`
- `POST /api/chat`，JSON body: `{"question": "Codex 使用了什么技术？", "mode": "terms", "expand": true, "top": 20}`

多轮请求可增加 `history` 字段，例如 `[{"role":"user","content":"介绍 Codex"},{"role":"assistant","content":"上一轮回答"}]`。仅允许按 user / assistant 交替排列的已完成轮次，最多 20 条消息、合计 32,000 字符；当前 `question` 单独发送。无 `history` 的旧客户端仍正常工作。

### Chat 执行助手

使用 Codex 时，页面默认启用“执行助手”。它通过 app-server 的动态工具协议调用宿主提供的 `kb_list_documents`、`kb_read_document`、`kb_query_graph`、`kb_reanalyze_document` 和 `kb_sync_note`。可以直接说“检查当前笔记为什么过时”“重新分析这条视频并回写”，也可以点击快捷按钮。窗口支持展开，执行记录显示成功／失败、备份位置和笔记路径。

API 使用 `agent: true` 开启此模式，`content_id` 指定当前资料；默认仍兼容旧客户端的普通问答。工具只操作知识库，不提供任意 shell、文件编辑或桌面控制。Codex 自身的只读沙箱不影响宿主工具的授权回写。

分析结果保存正文 SHA-256、正文字符数和分析版本；普通视频入库发现指纹缺失或不一致时重新提取。执行“重新分析并回写”会强制重新提取，提取成功后备份 SQLite 与 vault、替换该来源的旧关系、清理该来源独有且已无关系的旧节点，保留其他来源的数据。数据库事务与笔记回滚保护普通写入失败；备份位于数据库旁的 `backups/analysis-*`，可用于进程或机器异常退出后的恢复。Chat 只有在实际回写且验证成功时显示“已更新”，读取旧结果不会再显示更新提示。

`mode=phrase&expand=1` 会先匹配完整短语,再用短语里的词扩展命中节点;`expand=0` 是严格短语匹配。

## 里程碑(双模型对比用)

| | 内容 | 状态 |
|---|---|---|
| M1 | 数据源接入(Takeout CSV / 播放列表 / 163 URL 清单) | 骨架完成 |
| M2 | 内容获取(字幕 ✓ / Whisper 回退 ✓ / 正文抽取 ✓) | 已实现，受来源访问权限与转写质量影响 |
| M3 | LLM 处理层(摘要+重点+相关度+实体关系,structured output) | 完成 |
| M4 | 知识图谱(ontology 校验、SQLite 图存储、别名归并) | 完成 |
| M5 | 规则引擎 ✓ + 研究报告生成 ✗ | 部分 |
| M6 | Obsidian 输出 ✓ / 定时调度 ✗ / 增量去重(部分) | 部分 |

“完成”指骨架实现 + 单测通过;对比测试时两个模型从同一 commit 出发各自补全剩余部分。
