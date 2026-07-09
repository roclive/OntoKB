# ontokb — 稍后观看研究管线 + 知识图谱

把 **tech.163.com** 文章和 **YouTube 稍后观看**清单接入一条自动化管线:抓取全文/字幕转录 → LLM 生成摘要、重点、主题相关度 → 按 **ontology** 抽取实体关系写入**知识图谱** → **规则引擎**驱动自动整理(wiki 页、MOC、报告队列)→ 全部落入 **Obsidian vault**。

本仓库同时是 **Fable 5 vs GPT-5.5** coding 能力对比测试的载体,见 [docs/PRD.md](docs/PRD.md) 与 [docs/scorecard.md](docs/scorecard.md)。

## 架构

```
watch list / URLs ──► sources/ (yt-dlp 字幕 · 163 正文抽取)
                          │ raw_text
                          ▼
                      llm.py (claude-fable-5, structured output)
                          │ summary · key_points · relevance · entities · triples
                          ▼
        ontology/core.yaml ──校验──► graph.py (SQLite 三元组库, 别名归并)
                          │ facts
                          ▼
                      rules.py (前向链式规则引擎, rules/default.yaml)
                          │ actions
                          ▼
                      vault.py ──► Obsidian vault (Sources/Entities/Wiki/MOC/Reports)
```

## 快速开始

```bash
pip install -e ".[dev,llm,youtube,html]"
cp config/config.example.yaml config/config.yaml   # 填 interests 和数据源
pytest                                             # 19 个单测,无网络依赖

ontokb ingest "https://www.youtube.com/watch?v=..."   # 单条端到端
ontokb queue                                          # 批量入队
ontokb rules                                          # 跑规则引擎
ontokb status
```

需要 `ANTHROPIC_API_KEY`(或 `ant auth login`)。模型默认 `claude-fable-5`,可用 `ONTOKB_MODEL` 覆盖。

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
