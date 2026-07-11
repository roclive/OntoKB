# ontokb — 稍后观看研究管线 + 知识图谱

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
