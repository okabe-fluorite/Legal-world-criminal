# 专家审核包MANIFEST（DRAFT）

> 发给专家前冻结为只读包并计算每个文件SHA-256。A阶段包不得含标准答案和自动门禁总分；B阶段再补充对应材料。

## 运行身份

| 字段 | 值 |
|---|---|
| Git commit | `[填写]` |
| 模型/provider | `[填写]` |
| Prompt版本 | `[填写]` |
| run ID/生成时间 | `[填写]` |
| 法源manifest SHA | `[填写]` |
| 审核包生成者/日期 | `[填写]` |

## A阶段：独立判断

| 文件 | 内容 | SHA-256 |
|---|---|---|
| `A/TQ01_question_output_sources.pdf` | 问题、系统输出、权威来源/版本/逐字quote | `[填写]` |
| `A/TQ02_question_output_sources.pdf` | 同上 | `[填写]` |
| `A/TQ03_question_output_sources.pdf` | 同上 | `[填写]` |
| `A/独立法学专家审核表_A阶段.pdf` | A阶段空白签署表 | `[填写]` |

## B阶段：差异核对

| 文件 | 内容 | SHA-256 |
|---|---|---|
| `B/standard_answers.pdf` | 标准答案草案与制定依据 | `[填写]` |
| `B/automatic_gate_report.pdf` | 自动要点/引用门禁，不称专家准确率 | `[填写]` |
| `B/source_manifest.json` | 来源URL、版本、SHA与系统run | `[填写]` |
| `B/独立法学专家差异复核表_B阶段.pdf` | 锁定A阶段后的差异复核表 | `[填写]` |

## 整改复签（如适用）

| 文件 | 内容 | SHA-256 |
|---|---|---|
| `revision/专家整改复签记录.pdf` | old/new run、修改项、重跑门禁、复签结论 | `[无则写NA]` |

包级SHA-256：`[填写]`
