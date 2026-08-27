# Model Adapter 与微调小模型接入

业务代码统一通过 `backend/src/utils/model_config.py` 选择模型。所有端点均采用
OpenAI-compatible `/chat/completions` 协议，因此可接入 vLLM、SGLang、
Xinference、Ollama 网关或云端微调模型。

## 任务路由

支持以下任务：

| task | 用途 |
|---|---|
| `agent` | 检察官、法官、当事人等案件Agent |
| `teaching_judge` | 八能力Rubric教学裁判 |
| `citation_alignment` | 法条与学生论断的引用对齐裁判 |
| `response_assist` | 学生表达润色/低风险辅助 |
| `document_assist` | 辩护词等文书辅助 |
| `closing_summary` | 单案结案反馈 |
| `eval` | 离线评测裁判 |

默认全部使用 `.env` 中的 `OPENAI_*` 主模型。微调小模型只接管显式列出的任务：

```dotenv
SIMLAW_SMALL_MODEL_API_KEY=local-or-hosted-key
SIMLAW_SMALL_MODEL_API_BASE_URL=http://127.0.0.1:8001/v1
SIMLAW_SMALL_MODEL_NAME=criminal-law-tutor-7b-lora
SIMLAW_SMALL_MODEL_TASKS=teaching_judge,citation_alignment,response_assist
SIMLAW_SMALL_MODEL_TIMEOUT_SECONDS=180
```

要为单个任务配置专门端点，使用：

```dotenv
SIMLAW_MODEL_TEACHING_JUDGE_NAME=criminal-judge-7b
SIMLAW_MODEL_TEACHING_JUDGE_API_BASE_URL=http://127.0.0.1:8002/v1
SIMLAW_MODEL_TEACHING_JUDGE_API_KEY=local-key
SIMLAW_MODEL_TEACHING_JUDGE_TIMEOUT_SECONDS=180
```

优先级为：调用方显式值 > 单任务配置 > 小模型任务列表 > `OPENAI_*`主模型。

## OpenCode优先与DeepSeek官方自动回退

可同时配置主端点和fallback：

```dotenv
OPENAI_API_BASE_URL=https://opencode.ai/zen/go/v1
OPENAI_API_KEY=...
OPENAI_MODEL_NAME=deepseek-v4-flash

SIMLAW_FALLBACK_MODEL_API_BASE_URL=https://api.deepseek.com
SIMLAW_FALLBACK_MODEL_API_KEY=...
SIMLAW_FALLBACK_MODEL_NAME=deepseek-v4-flash-vision-exp
SIMLAW_FALLBACK_MODEL_TIMEOUT_SECONDS=180
SIMLAW_FALLBACK_CIRCUIT_SECONDS=900
```

正常请求始终优先OpenCode。只有429/用量窗口、502—504、超时和连接中断等瞬态错误才自动回退；第一次失败后按主端点主机开启进程内共享熔断，避免每个新Agent重复撞限流。401、400、模型名错误等配置问题不会被fallback静默掩盖。`GET /api/model/catalog`只展示主/备模型名、端点主机、是否配置和熔断状态，不返回Key或URL私有路径。

要为单任务指定不同fallback，可配置`SIMLAW_MODEL_<TASK>_FALLBACK_NAME`、`_FALLBACK_API_BASE_URL`、`_FALLBACK_API_KEY`和`_FALLBACK_TIMEOUT_SECONDS`。

## 安全状态接口

登录后访问：

```text
GET /api/model/catalog
```

返回每个任务实际选用的provider、模型名、端点主机及“是否配置密钥”，不会返回
API Key或URL私有路径。不要在日志、前端或错误响应中打印完整ModelEndpoint。

## 小模型验收

微调模型进入正式路由前，至少完成：

1. 独立金标准集，与主模型/Prompt/RAG基线比较；
2. JSON格式遵循、拒答、引用忠实度和法学专家评分；
3. 低置信度时回退主模型或教师复核；
4. 延迟、吞吐、显存和成本记录；
5. 保留模型卡、训练数据版本、基座、LoRA参数和许可证。

现行法、司法解释和案例更新始终由法源/RAG维护，不允许依靠小模型参数记忆替代。
