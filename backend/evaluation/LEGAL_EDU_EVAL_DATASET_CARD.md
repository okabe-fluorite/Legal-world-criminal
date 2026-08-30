# LegalEduEval-v1 Candidate Dataset Card

## 定位

LegalEduEval-v1是本科刑法场景的模型无关候选评测集，用于统一比较基础模型、Prompt/Few-shot、可信RAG和队友微调模型。当前版本不是法学教师Gold，也不用于训练。

## 规模与切分

- 总计100题：法源25、争点涵摄25、正反论证20、教学反馈15、安全弃权15。
- dev 30 / test 70；按`source_family_id`整体切分，跨split来源家族重叠0。
- 每题包含Evidence、required points、forbidden outputs、风险标签、自动指标、人工Rubric、审核状态、来源与内容SHA。

## 来源

题目只由当前仓库受治理的10张KnowledgeCard、30道TaskItem和22条正式课程Evidence派生。LawBench、LexEval、MSLR-Bench和LeCaRDv2只提供任务分类、Runner、IRAC/FRC或检索评测方法启发；旧模型输出、外部答案和案件全文没有复制为Gold。

## 评测状态

| 条件 | 当前状态 |
|---|---|
| E0基础模型 | pending |
| E1 Prompt/Few-shot | pending |
| E2可信RAG | pending |
| E3 RAG+队友微调模型 | pending_model_delivery |
| 法学教师逐题审核 | pending |
| 学习效果 | not_evaluated |

## 污染与许可

- 100题声明为`evaluation_only_not_for_training`。
- 25道涵摄题与产品TaskItem同源；如果队友训练manifest包含这些任务或近似变体，相应测试必须标`contaminated`并替换为独立教师命题。
- 来源家族切分防止当前集内部直接泄漏，但不能证明模型预训练阶段没有见过相似法律题。
- 当前内部受治理内容可用于比赛候选评测；对任何后续外部数据复用须逐项目核验许可证。

## 指标边界

Runner可计算Schema成功、required point覆盖、Evidence范围、逐字quote、禁止输出、应弃权行为、延迟、token和费用。关键词与引文门禁不是法律语义正确性；专家评分和教学效度必须由真实人员与课堂研究补齐。

## 可复现

```powershell
python -X utf8 backend/scripts/build_legal_edu_eval_v1.py
python -X utf8 backend/scripts/run_legal_edu_eval_v1.py
```

权威结构文件：`legal_edu_eval_v1.jsonl`、`legal_edu_eval_v1_manifest.json`、`schemas/legal-edu-eval-item-v1.schema.json`。
