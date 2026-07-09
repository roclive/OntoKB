# PRD(冻结版 v1)— 稍后观看研究管线

> 本文档是 Fable 5 vs GPT-5.5 对比测试的统一需求输入。测试开始后不得修改;
> 两个模型从同一 commit 出发,在各自分支上按里程碑实现,逐字使用相同指令。

## 目标

个人自用的内容研究管线:自动消化 YouTube 稍后观看和网易科技文章,
产出摘要/重点/研究报告,并沉淀为 ontology 约束的知识图谱 + Obsidian 知识库。

## 里程碑与验收标准

### M1 数据源接入
- 支持 Google Takeout 导出的 Watch later CSV 解析(注意 Takeout 无官方 API)。
- 支持 yt-dlp 可读的播放列表 URL(可选 cookies)。
- 支持 config 中的 163 文章 URL 清单;`ontokb queue` 将全部条目写入 contents 表,重复入队幂等。
- 验收:给定样例 CSV(10 条)与 3 个 163 URL,queue 后 status 显示 contents=13;重复 queue 不增加。

### M2 内容获取
- YouTube:优先官方/自动字幕(zh-Hans > zh > en),VTT 转纯文本去重;无字幕时下载音频用 faster-whisper 转录(≤30 分钟视频)。
- 163:正文抽取,去广告/脚本,标题正确;编码兼容(GBK/UTF-8)。
- 失败重试 ≥2 次,失败条目 status=failed 且记录原因。
- 验收:5 个真实视频(至少 1 个无字幕)+ 3 篇文章全部拿到 raw_text;无字幕视频走 Whisper。

### M3 LLM 处理层
- 一次 structured-output 调用产出:summary、key_points、topics、对 config.interests 的 relevance(0-1)、entities、triples(带 evidence 引用)。
- 模型 claude-fable-5(对照组用 GPT-5.5 等价 API),开启 refusal fallback。
- 验收:输出通过 pydantic 校验;抽取的三元组 ontology 校验通过率 ≥80%(抽样人工核对)。

### M4 知识图谱
- 实体按规范化名称与别名归并;三元组经 ontology domain/range 校验后入库,拒绝项记日志。
- 支持查询:实体度数、邻接关系、按类型列实体。
- 验收:现有单测全绿;跨 3 篇内容提到同一实体时图中只有一个节点。

### M5 规则引擎 + 研究报告
- 规则 YAML 声明,前向链式推理,最大轮数与动作去重(已有骨架)。
- 报告生成:聚合 Reports/_queue.md,按主题分组,每主题一次 LLM 调用产出跨源 report
  (趋势、共识、分歧观点、值得深挖的问题),写入 Reports/YYYY-WW.md。
- 验收:规则单测全绿;对 ≥5 条已处理内容生成一份报告,报告中每个论点附来源链接。

### M6 自动化与落地
- Obsidian 输出(已有骨架):Sources/Entities/Wiki/MOC/Reports 五区,类型化双链。
- 定时调度:Windows 任务计划或 cron 脚本,每日 queue→fetch→ingest→rules,增量去重(已处理内容跳过)。
- 验收:连跑两天,第二天不重复处理第一天的内容;vault 在 Obsidian 中打开 graph view 正常。

## 约束

- Python ≥3.10;新增依赖需在 pyproject 可选组里声明。
- 不允许绕过 ontology 校验直接写图。
- 抓取失败记为环境问题,不计入模型评分(见 scorecard)。

## 评分

见 [scorecard.md](scorecard.md)。每个里程碑双跑,7 维度加权。
