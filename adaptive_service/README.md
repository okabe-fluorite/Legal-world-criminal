# EduBrain刑法自适应服务

独立FastAPI服务，接收LegalWorld的`edubrain-learning-event-v2`，使用SQLite幂等记账，维护能力/知识证据画像，并从30道教师批准试用题中返回下一任务。

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

当前服务使用保守混合证据规则；后续可在内部加入ORCDF推理，但API和数据库事件合同保持不变。案件能力证据不是校准后的ORCDF掌握概率。

