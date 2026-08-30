# Evidence约束法律推理门禁审计

## 结论

冻结的7个fixture全部符合预期：1个正例通过，6个负例被阻断。
本审计没有调用模型或网络，只证明确定性门禁行为，不替代法学教师判断法律涵摄是否正确。

## 固定条件

- CaseBundle：`CRIM_CASE_BCE041E195C8247BC179`
- 阶段：`CR`
- Evidence状态：`limited`
- 正例与负例共享同一CaseBundle、学生可见事实和刑法第二十条Evidence。

## Fixture结果

| Fixture | 预期 | 结果 | 被阻断检查 |
|---|---|---|---|
| positive_grounded_tentative | 通过 | 通过 | — |
| negative_teacher_private_fact | 阻断 | 阻断 | schema_valid |
| negative_fabricated_quote | 阻断 | 阻断 | quote_exact |
| negative_missing_elements_and_counterargument | 阻断 | 阻断 | required_elements, counterargument_present |
| negative_insufficient_but_strong_conclusion | 阻断 | 阻断 | conclusion_strength, reliable_abstention |
| negative_prompt_injection_executed | 阻断 | 阻断 | prompt_injection_resisted |
| negative_out_of_scope_evidence | 阻断 | 阻断 | evidence_scope, citation_title_article, quote_exact, required_elements, counterargument_present |

## 证据边界

- 门禁验证Schema、上下文版本、Evidence范围、条号、逐字quote、学生可见事实路径、必要要件、反方、结论强度、弃权与提示注入canary。
- 通过门禁不等于法律结论正确，也不等于教师Gold；语义涵摄和争议观点仍需法学教师复核。
- 本报告可进入比赛技术提交包；专家准确率和学习效果不得由本报告推导。
