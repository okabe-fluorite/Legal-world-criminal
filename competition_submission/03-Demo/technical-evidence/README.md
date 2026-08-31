# 技术证据 Demo 截图与机器报告

本目录保存“技术证据”真实 Demo 入口的去标识验收材料，用于技术主线视频第 10—84 秒和作品方案第 4、6、7、8 页。

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
- 页面从 6 份权威 JSON/manifest 读取安全投影并在后端重新计算 SHA-256，不依赖前端常量填写实验结果。
- 自动 Gate 是软件机制证据，不是法学专家准确率。
- LegalEduEval-v1 的 100 题仍为 `candidate_requires_legal_review / not_gold`。
- Agent 结果来自一个固定条件 run，只支持“反方观点增加 1 条且成本显著增加”，不证明普遍优越性。
- Qwen3-8B 队友模型、教师 Gold、双教师盲评、真实用户和伦理签字仍为 `pending`。

## SHA-256

| 文件 | SHA-256 |
|---|---|
| `desktop-01-overview.png` | `26b3655049ba886dc6d501bb5c1d9941bf2f2c89918f4c0e4f26c8d70cd7c136` |
| `desktop-02-data-governance.png` | `ebe56cc7a9b0c2dc99772bcf129b090a84c261ec8e08cb7d23552416dfc80d74` |
| `desktop-03-reasoning-eval.png` | `4a9f0065ee07f76c5d0b21661ddd207310209b0b50c7ba7ee08c8be485ff26ed` |
| `desktop-04-agent-boundary.png` | `adaf8d8745ef6cd49acb970e8401e4201e6ae36f8da05333c2269d119feddacf` |
| `desktop-report.json` | `b85b11b92516ae9aaa44e7543c6f95b10ecc16658eae5b866c9bc0f622cabbb8` |
| `narrow-04-agent-boundary.png` | `d0102f88cb7439d92ab5d87a257e54265300d6f741cafc57203e127ee3ef915d` |
| `narrow-report.json` | `06a25f9b4fde738707405b04591479eeac6bf5ad19c7269a757727592d83ddec` |
