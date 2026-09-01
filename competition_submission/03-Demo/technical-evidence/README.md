# 技术证据 Demo 截图与机器报告

本目录保存“技术证据”真实 Demo 入口的去标识验收材料，用于技术主线视频第 10—84 秒和作品方案第 4、6、7、8 页。

页面顶部明确标注“比赛 / 答辩只读视图”：它用于集中展示数据治理、推理门禁、LegalEduEval、Agent消融、哈希和pending边界，不参与学生作答、评分、LearningEvent或长期画像。它不是第二套课程事实源，也不是学生学习页面。

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
| `desktop-01-overview.png` | `26112bfef20cce856e0be7d934f8d20223c67a00930cf36ca18f33b015992bf9` |
| `desktop-02-data-governance.png` | `9215ca72b252e823d7be001bd4d49329a7d52252016144555356aa253462054d` |
| `desktop-03-reasoning-eval.png` | `f446ee4b24455158485a158638b289c03b9e3a4e131d9f8ea51de006b93855df` |
| `desktop-04-agent-boundary.png` | `a42990e3e3a96a1922a7ed2ceb6517402a3bdb0de1c358dabd0c1afc8aa2494c` |
| `desktop-report.json` | `6a97a31a2f1cebdecf152f4b8b4059c03911726e794c5444f536dbd7e57218f2` |
| `narrow-04-agent-boundary.png` | `0e4ce387043f9f7d754f7cff60900e789cbd8ce02e6ff2df549e13d6c9cc0ad8` |
| `narrow-report.json` | `37e188987e6e0caa6c499afc64a5d342a5b106dd8e3fdf0602547a4950c13e96` |
