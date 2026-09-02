# 技术说明 Demo 截图与机器报告

本目录保存“技术说明”真实 Demo 入口的去标识验收材料，用于技术主线视频和作品方案中的数据、推理、评测与Agent说明。

页面顶部明确标注“比赛 / 答辩只读视图”：它用于集中展示数据治理、推理检查、LegalEduEval、Agent对比和下一步事项，不参与学生作答、评分、LearningEvent或长期画像。SHA、内部ID和文件审计细节不在界面展示，只保留在机器报告中。

## 文件

- `desktop-01-overview.png`：4,173 候选材料到 813 正式法源、11 项推理门禁、100 题候选评测和 4 个应用场景的总账。
- `desktop-02-data-governance.png`：刑法 505 条、刑诉法 308 条、L2/L3 候选、知识—Evidence 链接及 2024 版本链。
- `desktop-03-reasoning-eval.png`：结构化推理 Gate、1 个正例、6 个负例、LegalEduEval-v1 五类任务和 E0—E3 状态。
- `desktop-04-agent-boundary.png`：固定条件 C0/C1 的要件、反方覆盖、耗时、token、确定性归一和教师盲评状态。
- `narrow-04-agent-boundary.png`：780×900 基础窄屏的 Agent 成本分组。
- `desktop-report.json`、`narrow-report.json`：Playwright 结构、横向溢出、隐私字段、控制台、页面、HTTP 和请求失败检查结果。

## 验收边界

- 视口：1500×980 与 780×900。
- 两轮均为横向溢出 0、私有字段 0、console/page/HTTP/request 错误 0。
- 阶段13在用途提示和录屏字号增强后重跑：标签/说明/边界字号约12.5/10.9/10.4px，桌面与窄屏四页仍横向溢出0、私有字段0、console/page/HTTP/request错误0。
- 页面从 6 份权威 JSON/manifest 读取安全投影并在后端重新计算 SHA-256，不依赖前端常量填写实验结果。
- 自动 Gate 是软件机制证据，不是法学专家准确率。
- LegalEduEval-v1 的 100 题仍为 `candidate_requires_legal_review / not_gold`。
- Agent 结果来自一个固定条件 run，只支持“反方观点增加 1 条且成本显著增加”，不证明普遍优越性。
- Qwen3-8B 队友模型、教师 Gold、双教师盲评、真实用户和伦理签字仍为 `pending`。

## SHA-256

| 文件 | SHA-256 |
|---|---|
| `desktop-01-overview.png` | `e70212a4aa0c016848a8c219512e13d4be35d814c5658d280acd4bc7ad981888` |
| `desktop-02-data-governance.png` | `ec26dbb8ed3b2030c0ab5b81894b429bd6fe1b8f2a7c3054d7ee2d1437c39642` |
| `desktop-03-reasoning-eval.png` | `53362a8007be5298adcab7a1d24f6f94a227ef78aaf179591ebdeb45b7d470bc` |
| `desktop-04-agent-boundary.png` | `e7c884b0763492da84ceb140be024401a99ed8c71e43783a29fe2a4d32aa8405` |
| `desktop-report.json` | `a01be0fdb227aca7716ddb5ea3777666428eca435372ca89f0d03b561227ad7a` |
| `narrow-04-agent-boundary.png` | `00f48e020834a54c09150bfc2fb31b2c0468417ee4d933e99e08b0e664b4e4ad` |
| `narrow-report.json` | `dbbadcd5d6d6731360e835fb9feb03469a167e5f79e70886190e89be80f31677` |
