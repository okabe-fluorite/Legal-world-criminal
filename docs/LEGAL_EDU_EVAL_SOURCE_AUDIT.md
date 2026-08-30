# LegalEduEval-v1本地来源方法审计

## 结论

本项目没有把本地“结果测评”参考目录中的旧模型输出、公开题答案或案件全文复制为LegalEduEval Gold。首版100题只使用当前仓库受治理的刑法KnowledgeCard、TaskItem和正式Evidence生成候选题，并统一标记`candidate_requires_legal_review / not_gold`。

## 可借鉴但不直接搬运的本地项目

| 项目 | 本地事实 | 只借鉴什么 | 不采用什么 |
|---|---|---|---|
| LawBench | 20类中国法律任务，每类500题；本地目录混有`.venv`、预测结果和多来源数据 | 三层法律认知任务分类、任务专用解析、舍弃率 | 旧模型预测、未经现行法复核的答案、把多来源许可证统一解释 |
| LexEval | LexCog六类能力、23项任务、14,150题；本地约3GB主要来自1,748个模型输出JSONL | 能力分类、统一生成/评测Runner、自动与生成指标分离 | 历史模型输出、把通用法律能力直接当本科刑法教学效度 |
| MSLR-Bench | 本地约1,428个JSON，核心场景是内幕交易行政处罚；含IRAC/FRC/LLM评阅脚本 | 字段完整率、IRAC结构、失败案例记录、人工+机器结合 | 案件正文、个人地址信息、把证券行政处罚推理当刑法课堂Gold |
| LeCaRDv2 | 类案检索与相关性标注 | 检索评测思路 | 直接作为学生知识追踪或教学问答Gold |
| EduBrain记录 | 法律MOOC、LLM-Q、教师门禁、ORCDF和防泄漏实验 | 题族切分、哈希、失败隔离、同模型共错警示、pending语义 | 把民法/宪法行为迁移结果说成刑法课堂效果 |

## 首版100题组成

| 类型 | 数量 | 主要内部来源 |
|---|---:|---|
| 法源与可追溯问答 | 25 | 22条正式Evidence + 3个错误条号负例 |
| 争点与要件涵摄 | 25 | 25个受治理TaskItem派生候选 |
| 正反论证与案件推理 | 20 | 10个KnowledgeCard × 2个反方/边界任务 |
| 教学追问与错因反馈 | 15 | TaskItem误概念字段派生的学生错误回答 |
| 安全、拒答和证据不足 | 15 | 10个提示注入/教师冒充 + 5个事实不足强结论 |

## 防泄漏与污染边界

- split按`source_family_id`分组，dev 30、test 70，跨split来源家族重叠为0；不是随机逐题切分。
- 100题只能用于评测，不能回流训练。25道涵摄题由产品TaskItem派生；若队友训练数据包含同源TaskItem或近似改写，必须把相应成绩标为`contaminated`并替换为独立命题。
- 当前required points是机器检查候选，不是教师Gold；法学教师需逐题核对法源时效、答案、争议边界、禁止结论和Rubric。
- 自动关键词覆盖、条号与逐字quote只能证明格式与Evidence纪律，不能证明规范涵摄正确。
- 评测集不含真实学生学习日志，不能用于宣称学习增益或路径效果。

## 可复现入口

```powershell
cd <Legal-world-criminal仓库根目录>
.\.venv\Scripts\python.exe -X utf8 backend\scripts\build_legal_edu_eval_v1.py
.\.venv\Scripts\python.exe -X utf8 backend\scripts\run_legal_edu_eval_v1.py
```

队友模型交付前，E0/E1/E2保持`pending`，E3保持`pending_model_delivery`。
