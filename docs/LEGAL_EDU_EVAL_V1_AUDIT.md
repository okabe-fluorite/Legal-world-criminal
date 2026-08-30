# LegalEduEval-v1候选评测审计

## 数据集

- 候选题：100题
- split：dev 30 / test 70
- 跨split来源家族重叠：0
- 当前状态：candidate_requires_legal_review / not_gold

## E0—E3状态

| 方案 | 状态 | 自动门禁率 | 人工评分 |
|---|---|---:|---|
| E0_base_model | pending | — | pending |
| E1_prompt_few_shot | pending | — | pending |
| E2_trusted_rag | pending | — | pending |
| E3_rag_finetuned_model | pending_model_delivery | — | pending |

## 证据边界

- 当前报告验证100题结构、数量、来源家族隔离和Runner pending语义，不包含虚构模型成绩。
- 自动关键词/引文门禁不能替代法学教师对争点、涵摄、反馈和争议观点的评分。
- E3等待队友Qwen3-8B模型交付；交付前保持pending_model_delivery。
- 本评测不证明学生学习效果。
