# 法律全库混合RAG、教材RAG与题目检索计划

## 0. 状态

这是实施计划，不是完成报告。

本轮已经完成只读盘点，但尚未：

- 修改业务代码；
- 调用SiliconFlow API；
- 上传法律、教材或题目文本；
- 创建向量文件或索引；
- 运行混合检索实验。

后续只有用户确认计划后才进入实施。

## 1. 三个问题的直接结论

### 1.1 法律RAG

需要升级为混合检索并进行候选重排：

```text
BM25F稀疏检索
+ SiliconFlow Qwen/Qwen3-Embedding-8B稠密检索
→ RRF融合
→ 类型/时效/权威层级过滤
→ Reranker重排
→ EvidencePack
```

Reranker不是可有可无的展示层：它必须对BM25F与Dense融合后的候选进行最终排序；Reranker不可用时降级到RRF，Embedding不可用时降级到BM25F，任何降级都要写入检索trace和评测报告。

范围覆盖`<EDUBRAIN_ROOT>\laws`中的全部唯一法律、行政法规、司法解释/司法文件和案例。

“全部”指全部经过解析、去重并保留来源的canonical文档，不是把原始DOCX、派生TXT、ZIP、分类汇总和缓存重复索引多次。

### 1.2 题目是否需要Embedding

需要，但用途不是判分，而是：

- 相似题召回；
- 同知识点变式题推荐；
- 错因相似题检索；
- 题目到教材章节/法条的候选映射；
- 冷启动时形成任务候选。

当前产品正式题只有30道客观题和13道主观题，单独为这43题建立向量库价值有限；当接入CAIL/JEC-QA及其他候选题池后，Embedding才有明显价值。

Embedding不能替代正确答案、Q矩阵、Rubric、教师门禁或Evidence-KT。

### 1.3 是否加入书籍

需要，作为独立“教材解释层”，不能与现行法律规范混为同一权威层。

已找到：

`<EDUBRAIN_ROOT>\数据集\JEC-QA\reference_book\`

| 学科 | 文件数 | 约总大小 |
|---|---:|---:|
| 刑法 | 40 | 1.14MB |
| 刑事诉讼法 | 24 | 1.32MB |
| 宪法 | 6 | 0.51MB |
| 法理学 | 4 | 0.34MB |
| 司法制度和职业道德 | 6 | 0.66MB |
| 中国法律史 | 6 | 0.31MB |
| 法治理论 | 3 | 0.07MB |

`数据集 - 副本/JEC-QA/reference_book`是重复副本，默认只索引`数据集`中的一份。当前未发现其他明确独立的法学PDF/EPUB/MOBI教材。

优先索引刑法和刑诉法，其他学科后置。

## 2. 当前数据盘点

### 2.1 `laws`

当前约4,173个物理文件、约255MB：

| 目录 | 数量 | 计划用途 |
|---|---:|---|
| `output_laws` | 335 TXT | 法律canonical候选 |
| `output_regulations` | 610 TXT | 行政法规canonical候选 |
| `output_judicial` | 549 TXT | 司法解释/司法文件canonical候选 |
| `output_cases` | 530 TXT | 案例canonical候选 |
| `output_categories` | 60 TXT | 分类导航，不直接进入权威片段 |
| `raw_data` | 2,041 | 来源追溯和重建，不与派生文本重复索引 |
| 原始ZIP/脚本/缓存 | 其余 | 不作为内容块 |

第一版全库范围以四个`output_*`目录的唯一文本为主，并把原始文件路径和SHA保存在manifest中。

### 2.2 题目/问答候选

| 数据 | 当前规模 | 计划用途 |
|---|---:|---|
| 产品TaskItem | 30客观题 | 正式学生任务 |
| 产品SubjectiveTask | 13主观题 | 正式形成性任务 |
| CAIL/JEC-QA司法考试 | 7,775单选+13,297多选 | 题库候选/评测 |
| 其中显式`subject=刑法` | 278+863=1,141 | 优先刑法题候选 |
| 法律赛题训练集 | 1,600 | 宽领域问答候选 |
| DISC-Law Pair QA | 79,692 | 宽领域问答/教师备题候选 |
| DISC-Law Triplet QA | 23,331 | 带reference的RAG/评测候选 |
| 刑法Basic SFT | 595 | 候选，需内容门禁 |
| 刑法Case SFT | 200 | 案例题候选，需内容门禁 |
| 裁判要素`train.txt` | 6,959 | 要素/案件检索，不是普通题库 |
| MOOCCubeX高行为题 | 590可训练 | 民法/宪法行为迁移，不是刑法题库 |

这些数据不能一次性进入学生正式题库。计划分为`candidate`、`teacher_reviewed`、`published`三级。

## 3. 三库分离架构

```text
                 ┌─ legal_authority ─────────────────────┐
用户查询 → 路由 ├─ textbook_explanation ────────────────┼→ 分层Evidence → 模型回答
                 └─ question_teaching/public|private ─────┘
                          │
                 Sparse + Dense + RRF
```

### 3.1 法律权威库

逻辑分区：

```text
legal_laws
legal_regulations
legal_judicial
legal_cases
```

回答权威优先级：

```text
现行法律/行政法规/司法解释
> 受治理案例的裁判规则
> 教材解释
> 模型一般知识
```

### 3.2 教材解释库

逻辑分区：

```text
textbook_criminal_law
textbook_criminal_procedure
textbook_other_law
```

教材只用于白话解释、理论争议、概念边界、易错点和章节资源推荐。输出必须标为“教材解释”，不能冒充官方法条。

### 3.3 题目教学库

必须隔离：

```text
question_public：题干、选项、题型、章节、知识点、难度候选
question_private：答案、解析、误概念、Rubric、教师备注
```

学生端只允许访问`question_public`。服务端判分和教师端才能读取`question_private`。

## 4. Canonical数据Schema

### 4.1 法律/案例块

```json
{
  "chunk_id": "...",
  "document_id": "...",
  "source_type": "law|regulation|judicial_interpretation|case",
  "title": "...",
  "article_ref": "...",
  "case_id": "...",
  "issuing_authority": "...",
  "promulgated_date": "...",
  "effective_date": "...",
  "effective_status": "effective|expired|unknown",
  "section_type": "article|facts|issue|rule|reasoning|holding",
  "content": "...",
  "source_path": "relative/path",
  "source_snapshot_id": "...",
  "content_sha256": "..."
}
```

### 4.2 教材块

```json
{
  "chunk_id": "...",
  "source_type": "textbook_explanation",
  "subject": "刑法",
  "chapter_no": "第四章",
  "chapter_title": "犯罪排除事由",
  "section_title": "...",
  "content": "...",
  "related_knowledge_ids": [],
  "related_article_refs": [],
  "source_path": "relative/path",
  "content_sha256": "..."
}
```

### 4.3 题目块

```json
{
  "question_id": "...",
  "visibility": "public|private",
  "source_dataset": "CAIL2020_JECQA",
  "subject": "刑法",
  "question_type": "single|multiple|subjective|case",
  "stem": "...",
  "options": {},
  "knowledge_ids": [],
  "ability_tags": [],
  "difficulty_candidate": null,
  "answer_private": null,
  "rationale_private": null,
  "content_sha256": "..."
}
```

公开索引生成前必须删除/置空私有字段，不能只依赖前端隐藏。

## 5. 分块规则

### 5.1 法律和行政法规

- 一条一块；
- 过长条文按款/项拆分，保留父条号；
- Embedding文本包含法名、条号、章名和正文；
- 精确条号查询必须保留主键命中。

### 5.2 司法解释

- 按解释条款/要点分块；
- 保留解释对象、适用范围和发布机关；
- 无法识别条款结构时再使用长度分块。

### 5.3 案例

不能整案一个向量，采用父子分段：

```text
基本事实
争点
证据/关键事实
裁判规则
裁判理由
结果
引用法源
```

- `document_id`对应整案；
- `parent_id`对应“摘要/基本案情/裁判规则/裁判理由/结果/引用法源”等完整语义父段；
- BM25F、Embedding和Reranker处理父段下的短子块；
- 子块命中后按`parent_id`回填完整父段，并可取同案相邻父段；
- `case_parents.jsonl`与子块的`parent_id`必须一一校验，禁止孤儿子块或跨案父段。

### 5.4 教材

- 先按章节/小节；
- 小节过长时按600—1,000个中文字符切块；
- 重叠约100—150字符；
- 每块重复写入学科、章节和小节标题。

### 5.5 题目

- 一题一公开记录；
- Embedding文本为题干+选项+题型+公开知识点；
- 正确答案和解析不进入学生可见Embedding文本；
- 私有答案索引如有需要，必须是独立文件和权限域。

## 6. SiliconFlow Embedding计划

`.env.example`当前SiliconFlow段已配置：

```text
model = Qwen/Qwen3-Embedding-8B
baseurl = https://api.siliconflow.ai
api_key = 已配置但不显示
```

SiliconFlow官方接口示例使用`POST https://api.siliconflow.cn/v1/embeddings`。实施时不能直接猜测`.ai`和`.cn`的兼容性，先做不含隐私内容的小样本连通性探针。[SiliconFlow Embeddings文档](https://docs.siliconflow.cn/en/api-reference/embeddings/create-embeddings)

建议映射到项目私有`.env`：

```dotenv
LAW_EMBEDDING_API_KEY=<本地设置>
LAW_EMBEDDING_API_BASE_URL=https://api.siliconflow.cn/v1
LAW_EMBEDDING_MODEL=Qwen/Qwen3-Embedding-8B
LAW_EMBEDDING_DIMENSIONS=1024
```

这只是计划字段，不在当前轮写真实值。

### 6.1 小样本探针

先选择200—500个已规范化块，测试：

- URL和鉴权；
- 批量输入；
- 1024维返回；
- token/费用；
- p50/p95延迟；
- 429/503/504/超时；
- 空向量/NaN/维度漂移；
- 同内容hash缓存；
- API失败后BM25F仍可工作。
- Reranker候选输入、返回排序、超时/429/维度或Schema错误；Reranker失败后RRF结果必须保持可用。

模型允许较长输入不代表应该把整案或整章一次Embedding；必须先分块。

### 6.2 全量构建

小样本通过后生成：

```text
rag_indexes/
├── legal_authority_v1/
│   ├── metadata.jsonl
│   ├── embeddings.float16.npy
│   └── manifest.json
├── textbook_v1/
├── question_public_v1/
├── question_private_v1/
└── build_log.jsonl
```

manifest必须包含：

- embedding模型和维度；
- 文本预处理/分块版本；
- 输入总数、成功、失败和重试；
- 每个源文件/块hash；
- 向量文件hash；
- 构建时间和代码commit；
- API响应模型名和维度检查。

## 7. 运行时混合检索

### 7.1 查询路由

| 查询 | 目标库 | 策略 |
|---|---|---|
| 明确法名/条号 | 法律 | BM25F/主键优先，Dense补充 |
| 概念辨析 | 法律+教材 | Sparse/Dense并行+RRF |
| 案情到规范 | 法律+案例 | Hybrid+权威过滤 |
| 相似案例 | 案例 | Dense+罪名/时间过滤 |
| 教材解释 | 教材+法律 | 教材解释，法律校验 |
| 相似题/变式题 | 题目公开 | Dense+知识点/题型过滤 |
| 无答案/越界 | 分层库 | 允许明确弃权 |

### 7.2 召回顺序

1. 归一化法名、条号、罪名和查询；
2. 按`source_type/effective_status/subject/question_visibility`过滤；
3. BM25F召回Top20；
4. SiliconFlow Query Embedding召回Top20；
5. 用Reciprocal Rank Fusion融合，不直接相加BM25和余弦分；
6. 按document/article/case去重；
7. 用Reranker对RRF Top20重排；
8. 输出Top5—8候选；
9. 运行条号、quote、时效、Evidence范围和NLI/教师门禁；
10. 生成EvidencePack，记录每条候选来自Sparse、Dense或两者。

### 7.3 精确条号保护

查询含明确条号时：

- 主键/BM25F命中不得被Dense结果挤掉；
- 教材和案例只能补充解释；
- 最终法条必须展示法名、条号、正文、版本和来源。

Reranker不得覆盖精确条号保护；明确法名/条号命中必须保留在最终TopK，除非该来源经过时效或准入门禁拒绝。

### 7.4 降级

- Hybrid通过feature flag启用；
- SiliconFlow失败、索引不存在或维度不一致时回退BM25F；
- Reranker失败、超时或返回非法排序时回退RRF；
- 没有真实索引时不能把`semantic_vector`显示为ready；
- Embedding失败不阻断学生作答、教师审核和案件流程。

## 8. 题目Embedding的实施边界

### 8.1 第一优先级

先处理：

- 30道产品客观题；
- 13道产品主观题；
- CAIL/JEC-QA中1,141道显式刑法题；
- 经门禁后再考虑595+200刑法SFT候选。

DISC-Law宽领域问答和64,525条`train.jsonl`不直接进入学生题库，只作教师备题/训练或评测候选。

### 8.2 推荐算法

```text
知识点/Q矩阵硬过滤
→ 已完成题排除
→ 题型/难度/阶段过滤
→ Embedding相似度或多样性排序
→ 教师约束
→ 推荐解释
```

Embedding是候选排序的一部分，不取代Q矩阵和学习状态。

### 8.3 答案隔离

- 学生Query Embedding只搜索`question_public`；
- 推荐接口不得返回答案/解析/Rubric；
- `question_private`的索引路径、API和缓存与公开索引分离；
- 自动测试要求答案泄漏率为0。

## 9. 教材RAG实施边界

优先刑法40章和刑诉法24章：

- 刑法总论章节优先映射到当前10个KnowledgeCard；
- 刑法各论用于扩展后续罪名；
- 刑诉章节映射LC/INV/PR/CR/CRA阶段；
- 教材解释必须与正式法源分卡展示；
- 教材文件缺少明确版本/作者信息时标记`edition_unknown`，只作教学参考。

典型回答结构：

```text
规范依据：刑法第二十条（法律Evidence）
案例规则：指导案例144号（案例Evidence）
教材解释：JEC-QA刑法第四章（教材解释）
争议/课堂口径：待教师复核
```

## 10. 评测计划

### 10.1 法律检索qrels

建立至少100—200个查询：

- 精确条号/法名；
- 概念改写；
- 案情到规范；
- 司法解释；
- 相似案例；
- 教材解释；
- 无答案/越界。

对比：

```text
R0 BM25
R1 当前BM25F+条号加权
R2 Dense Embedding
R3 BM25F+Dense RRF
R4 RRF+Reranker
```

指标：Recall@1/3/5/10、Precision@5、MRR@10、nDCG@10、无答案误召回率、p50/p95延迟。按查询类型和source_type分别报告。

### 10.2 Evidence/NLI

- 法源/条号有效率；
- quote逐字匹配；
- 权威层级和时效正确率；
- 关键主张Evidence覆盖率；
- 无依据主张率；
- 至少180对法条—论断三分类人工集；
- NLI Macro-F1、各类F1、混淆矩阵、冲突率、选择性准确率/coverage和校准。

### 10.3 端到端

比较无RAG、BM25F、Dense、Hybrid、Hybrid+NLI门禁：

- 专家答案正确性；
- faithfulness和答案相关性；
- Citation correctness/completeness；
- hallucinated statute rate；
- 应弃权未弃权率；
- 延迟和费用。

至少30—50题由两名法学人员盲评。

### 10.4 题目/教材

- 相似题Recall@k；
- 变式题教师相关性1—5；
- 知识点/章节映射准确率；
- 错因标签命中率；
- 题目答案泄漏率；
- 推荐重复率；
- 推荐后完成率/前后测变化只能来自真实用户。

## 11. 实施阶段

### 阶段1：库存与canonical manifest

- 只读读取四个`output_*`目录；
- 建立唯一文档和重复组；
- 建来源、时效、类型和隐私字段；
- 生成候选/准入/拒绝清单。

### 阶段2：分块候选

- 生成法律、司法解释、案例、教材和题目的chunk JSONL；
- 此阶段不调用Embedding API；
- 做Schema、hash、答案隔离和重复测试。

### 阶段3：评测集优先

- 建100—200个检索qrels；
- 建180对NLI人工标注模板；
- 先冻结指标，再跑模型。

### 阶段4：SiliconFlow探针

- 200—500块；
- 核验URL、维度、批量、成本、延迟和重试；
- 不通过则停止，不影响BM25F。

### 阶段5：向量索引

- 法律、教材、题目分批构建；
- 写float16向量、metadata和manifest；
- 支持断点续跑和按hash复用。

### 阶段6：Hybrid运行时

- Sparse/Dense/RRF/query router/feature flag；
- 接入EvidencePack；
- BM25F稳定fallback。

### 阶段7：教材与题目功能

- 分层教材引用；
- 相似题/变式题/错因检索；
- 学生端答案隔离。

### 阶段8：评测和展示

- R0—R4检索消融；
- Evidence/NLI/端到端评测；
- 权限和浏览器smoke；
- PPT图表、技术报告和视频指标卡。

## 12. PPT与视频

### PPT

建议两页：

1. `4,173库存→canonical治理→法律/教材/题目三库→BM25F+Qwen3-Embedding→RRF→Evidence`；
2. R0—R4 Recall/MRR/nDCG、Evidence覆盖、NLI、faithfulness、延迟。

所有数字标明查询数、人工标注数、索引版本和代码commit。

### 视频

只展示：

- 一次案情/概念查询；
- 法条、案例、教材分层结果；
- 一次错误引用或无答案请求被拒绝；
- 末尾3—5秒关键真实指标。

完整召回消融、NLI混淆矩阵和错误分析放PPT/效果报告，不在3分钟视频中讲完整。

## 13. 停止条件

- 100—200条qrels可复现；
- Dense/Hybrid是否优于BM25F有分类型真实结论；
- 精确条号召回不得退化；
- 法律、教材、题目三库结果层级清楚；
- 题目答案泄漏率0；
- SiliconFlow失败可回退BM25F；
- manifest、向量hash、模型/维度、Prompt、代码commit齐全；
- 未完成指标保持`pending`，不填模拟数字。
