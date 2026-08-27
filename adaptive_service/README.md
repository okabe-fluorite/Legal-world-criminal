# EduBrain刑法自适应服务

独立FastAPI服务，接收LegalWorld的`edubrain-learning-event-v2`，使用SQLite幂等记账，维护能力/知识证据画像，并从30道教师批准试用TaskItem中返回下一任务。

```powershell
$env:PYTHONPATH="$PWD\adaptive_service\src"
uv run --no-project --with-requirements adaptive_service\requirements.txt `
  python -m uvicorn edubrain_adaptive.api:app --port 8010
```

接口：

- `GET /health`
- `POST /events`
- `POST /recommend`
- `GET /profiles/{student_id}`

设置`SIMLAW_ADAPTIVE_API_KEY`后，除health外均要求Bearer凭据。

服务优先读取`data/task_items.jsonl`和`data/knowledge_cards.jsonl`受治理契约，并通过`data/q_matrix.jsonl`连接任务与知识点；旧`approved_items.jsonl`和`knowledge_nodes.jsonl`仅保留兼容。推荐返回`standard_evidence_ids`和内容版本，但始终删除`answer_private`、`rationale_private`、`misconceptions_private`，并返回`answer_included: false`。

KnowledgeCard、TaskItem、EvidencePack的完整契约见[`../docs/KNOWLEDGE_CONTRACTS.md`](../docs/KNOWLEDGE_CONTRACTS.md)。当前推荐任务尚不能直接提交作答；TaskAttempt判分与回写属于下一纵向切片。

当前服务使用保守混合证据规则；后续可在内部加入ORCDF推理，但API和数据库事件合同保持不变。案件能力证据不是校准后的ORCDF掌握概率。
