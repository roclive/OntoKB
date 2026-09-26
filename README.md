# ontokb — 稍后观看研究管线 + 知识图谱

## 阅读工作台与摘要漫游

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

当前每条消息处理第一个有效 YouTube 链接；其他消息查询知识库。Chat 仍是独立单轮问答，每轮需写清对象，不支持跨轮记忆、token 流式展示和工具审批。每次 Codex 调用超时 180 秒，下载/转写耗时另计。CLI 存在性检查不代表登录仍有效，可运行 `codex login status` 验证。

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

`mode=phrase&expand=1` 会先匹配完整短语,再用短语里的词扩展命中节点;`expand=0` 是严格短语匹配。

## 里程碑(双模型对比用)

| | 内容 | 状态 |
|---|---|---|
| M1 | 数据源接入(Takeout CSV / 播放列表 / 163 URL 清单) | 骨架完成 |
| M2 | 内容获取(字幕 ✓ / Whisper 回退 ✗ / 正文抽取 ✓) | 部分 |
| M3 | LLM 处理层(摘要+重点+相关度+实体关系,structured output) | 完成 |
| M4 | 知识图谱(ontology 校验、SQLite 图存储、别名归并) | 完成 |
| M5 | 规则引擎 ✓ + 研究报告生成 ✗ | 部分 |
| M6 | Obsidian 输出 ✓ / 定时调度 ✗ / 增量去重(部分) | 部分 |

“完成”指骨架实现 + 单测通过;对比测试时两个模型从同一 commit 出发各自补全剩余部分。
