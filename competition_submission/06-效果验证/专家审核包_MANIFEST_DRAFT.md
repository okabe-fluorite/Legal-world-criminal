# 三题独立法学专家审核包MANIFEST（DRAFT）

> 材料已生成，但真实专家尚未审核。必须先发送A阶段包并锁定签名表，之后才能披露B阶段包；不得把本manifest或自动门禁写成专家结论。

## 冻结身份

| 字段 | 值 |
|---|---|
| Git commit | `6deb1b8ff79cec011139c4bd038a63375a8a9188` |
| 模型/provider/任务 | `deepseek-v4-flash / primary / learning_support` |
| Prompt/报告版本 | `typical-question-evaluation-v1 / live_model_reaudited` |
| run生成时间 | `2026-08-29T00:17:02.490918+08:00` |
| 三题suite SHA-256 | `3b5f896c63fb6e207c59c5039876c8f35d6a823eeeb36ba7b2b0dc73c71180c2` |
| 法源manifest SHA-256 | `78360315a0e3b29f1c34bceeb3ccfde7ee75aa8b16c56efe3a8f20701f0e76d7` |
| 构建脚本 | `competition_submission/scripts/build_expert_review_package.py` |
| 构建日期 | `2026-08-30` |
| 构建审计 | 8份PDF、21页；A阶段盲审隔离通过；秘密扫描通过；专家状态仍为`false` |

## A阶段：独立判断

只发送`专家审核包_DRAFT/A阶段_独立判断包_DRAFT.zip`及同名SHA文件。

| 文件 | 内容 | SHA-256 |
|---|---|---|
| `A/TQ01_question_output_sources.pdf` | 问题、系统输出、权威来源/版本/逐字quote | `2ce83aa5bdeb9004ae4c903fa40a5ce64e7e5bdb8231782e49cc8e6946a73fe8` |
| `A/TQ02_question_output_sources.pdf` | 同上 | `87ecb80bed6dc9f3e6cb37711fa33c3d1c8524ad3bc1535afdf4d5b9da75e083` |
| `A/TQ03_question_output_sources.pdf` | 同上 | `f7d8e2ae475d30afbcd5da9a313eef5eeffebae2a162a1438194a811e1feff32` |
| `A/独立法学专家审核表_A阶段.pdf` | 三题盲判、A阶段锁定与签名表 | `1af4b905082d19a0e26d25c8d9cadee7f14f27031173d0d5f6a9fe45eb4ea088` |

A阶段ZIP SHA-256：`c259b169e6f770de34d6c570f7b59328af5fd1d8c252b0ed6938ef0ea4684857`

## B阶段：差异核对

只有收到已签名、已计算SHA-256的A阶段表后，才能发送`专家审核包_DRAFT/B阶段_差异核对包_DRAFT.zip`及同名SHA文件。

| 文件 | 内容 | SHA-256 |
|---|---|---|
| `B/standard_answers.pdf` | 标准答案草案与制定依据 | `e669c00a909d4c8ede9a0c32676b7f33d0b39ebc633798214a65d45785a1aeda` |
| `B/automatic_gate_report.pdf` | 自动要点/引用门禁；3/3不称专家准确率 | `8a993505c9057a1c25c369bc896ff4cfccf6437b629fa0c0a5a282b3d5477145` |
| `B/source_manifest.json` | 去除密钥与私有字段的来源、模型、版本和SHA | `9ef035d17736ccd13852f904e6bc992a83d44949966e7de431b53198b1dfbacc` |
| `B/独立法学专家差异复核表_B阶段.pdf` | 锁定A阶段后的差异复核与签名表 | `77f53fc53852a166b0920d68549e3a467b07eca6d599c85d3d0f20ceb5fe8c6d` |

B阶段ZIP SHA-256：`ba3975dcff18ba1a86fca2a88ff95ae24727d0a10cf4343a3968886ed56928ff`

## 整改复签（如适用）

| 文件 | 内容 | SHA-256 |
|---|---|---|
| `revision/专家整改复签记录.pdf` | old/new run、整改要求、重跑门禁与复签结论 | `1b57f6f0374fdac864b1b3ca9a8cc7754124a8661c12557ddffedea0c071aec7` |

## 构建门禁

- `BUILD_AUDIT.json` SHA-256：`b397e3c0451398a0a5d465cf0f32f1d294ea82bb589cb275450a5de93550b065`。
- A包条目固定为3题材料、A阶段表与`A_MANIFEST.json`，不含标准答案草案、必需得分点或自动门禁报告。
- B包必须在A阶段锁定后披露。
- 所有PDF均经Poppler逐页渲染检查；当前共21页，无标题断词、裁切、重叠、黑块或中文字体缺失。
- API Key、`api_key_configured`、私有绝对路径和`source_response_sha256`扫描均为0命中。
- 真实专家审核完成前，`expert_review_complete=false`，PPT与效果报告继续显示`PENDING`。
