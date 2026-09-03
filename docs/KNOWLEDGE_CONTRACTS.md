# 课程知识、任务与证据契约

本仓库把本科刑法课程内容冻结为三个版本化对象：KnowledgeCard、TaskItem和EvidencePack。它们共同解决知识点命名漂移、题目法源不可追溯、推荐答案泄漏以及检索结果被误称为法律结论的问题。

当前发布规模为10个KnowledgeCard、30个TaskItem、22个受治理Evidence目录项和30条Q边。它们适用于比赛演示和低风险试用，仍要求法学教师在每学期上线前复核；不能据此声称已经取得真实课堂学习效果。

## 三个冻结对象

### KnowledgeCard

Schema：`schemas/knowledge-card-v1.schema.json`

数据：`adaptive_service/data/knowledge_cards.jsonl`

KnowledgeCard以稳定`knowledge_id`描述课程核心知识点，包含章节、学习目标、知识摘要、法条引用、标准证据ID、先修关系、常见错误、理论口径、审核状态、版本和内容哈希。当前10个知识点均为`pilot_teacher_approved`，该状态只表示通过现阶段教师门禁，不等于跨学校通用金标。

### TaskItem

Schema：`schemas/task-item-v1.schema.json`

数据：`adaptive_service/data/task_items.jsonl`

TaskItem是可推荐和可作答的版本化教学任务。它绑定知识点、目标能力、难度、认知维度、适用阶段、Q边、标准证据、评分规则、审核记录、源题哈希和内容哈希。当前任务均为`diagnostic_item`，可用于`prestudy`和`review`；学生作答与回写闭环由后续TaskAttempt契约承载。

以下字段是服务端私有判分材料：

- `answer_private`
- `rationale_private`
- `misconceptions_private`

`GET /api/knowledge/tasks/{task_id}`和adaptive推荐会删除这些字段，并显式返回`answer_included: false`。任何新接口、缓存、日志或前端状态都不得返回或嵌入私有字段。完成服务端TaskAttempt判分后，系统才以公开反馈字段向当前登录学生返回正确选项和解析，详见[`TASK_ATTEMPT_CONTRACTS.md`](TASK_ATTEMPT_CONTRACTS.md)。

### EvidencePack

Schema：`schemas/evidence-pack-v1.schema.json`

静态证据目录：`adaptive_service/data/evidence_catalog.jsonl`

EvidencePack是一次检索请求的分层证据快照，记录查询、知识上下文、来源身份、允许用途、证据片段、法源位阶、条号、效力、版本、发布机关、官方来源、父段上下文、覆盖候选和风险提示。它现支持法律、行政法规、司法解释/司法规范性文件、指导性/典型案例、教材解释和公开学习资源；813条刑法/刑诉法只是刑法课程核心规范基线。

EvidencePack有意保留以下语义边界：

- BM25F/Dense/RRF/Reranker命中只表示检索相关性，不表示材料支持学生论断；
- `coverage.status`只能是`candidate_requires_semantic_audit`或`insufficient_evidence`；
- 引用审计能确定性验证法律名称、条号和逐字片段；
- `lexical_overlap`不能冒充法律蕴含，存在claim时必须标记`semantic_entailment_not_evaluated`；
- 法源层级固定为法律优先于行政法规和司法适用材料；案例、教材和题目不得覆盖规范依据；
- 案例检索子块命中后必须回填案情、裁判规则或理由父段，且不得包装成法条；
- `unresolved`材料可进入检索和演示，但必须显示“效力尚未完全核实”；
- 公开题只作`learning_resource`，私有答案层不检索、不Embedding；每学期真实课堂前仍须增量复核现行法状态。

### KnowledgeGraph × RAG

课程知识图使用10个KnowledgeCard节点与10条先修边回答“学什么、先学什么、下一步做什么”。`POST /api/knowledge/search`会自动或按请求匹配知识节点，把知识点名称、法条锚点和先修节点加入Hybrid RAG查询，并在`knowledge_context`中返回匹配节点、先修关系和扩展项。检索出的多来源Evidence再用于解释诊断依据和路径推荐；知识图本身不证明学生掌握，RAG命中本身也不证明法律结论。

## API

| 方法与路径 | 返回内容 | 安全与证据边界 |
|---|---|---|
| `GET /api/knowledge/catalog` | 10个KnowledgeCard、对象数量、内容与法源manifest哈希 | 不返回TaskItem私有判分字段 |
| `GET /api/knowledge/tasks/{task_id}` | 单个公开TaskItem | 删除答案、解析和误概念私有字段；未知ID返回404 |
| `POST /api/knowledge/search` | `evidence-pack-v1` | 最多10条检索结果；coverage只是待语义审查候选 |
| `POST /api/knowledge/audit-citations` | 条号、引用片段和词法候选审计 | 不宣称已经完成法律语义蕴含判断 |

检索示例：

```json
{
  "query": "刑法第二十条正当防卫的时间与限度",
  "task_type": "争点辨析",
  "top_k": 5,
  "knowledge_ids": ["CRIM_KP_..."],
  "key_judgments": ["防卫必须针对正在进行的不法侵害"]
}
```

引用审计示例：

```json
{
  "citations": [
    {
      "title": "刑法",
      "article_ref": "第二十条",
      "quote": "为了使国家、公共利益、本人或者他人的人身、财产和其他权利免受正在进行的不法侵害",
      "claim": "正当防卫要求存在正在进行的不法侵害"
    }
  ]
}
```

## 构建、审计与变更规则

三个内容对象由同一构建器从教师批准题库、Q矩阵、知识点目录和受治理法源生成：

```powershell
.venv\Scripts\python.exe -X utf8 backend\scripts\build_governed_learning_content.py
```

构建器会逐字核验题目引用片段、拒绝绝对本地路径、校验三个JSON Schema，并更新`adaptive_service/data/manifest.json`中的数量与SHA-256。内容变更必须遵循：

1. 先更新受治理源或教师审核决定，不手改哈希掩盖漂移；
2. 重新运行构建器和`backend/tests/test_knowledge_contracts.py`；
3. 检查所有公开投影不含三个私有字段；
4. 每学期复核法源效力、理论口径和教师审核状态；
5. LLM生成的知识点、Q边、题目或语义判断保持候选状态，未经教师门禁不得自动发布。

## 当前未覆盖范围

- 真实课堂题目的难度/区分度参数和大规模纵向作答；
- 法律蕴含模型或教师审核后的claim-level支持结论；
- 真实本科刑法课堂的知识追踪校准和路径干预效果；
- 现有10节点课程图之外的全刑法章节级教师审定知识图。
