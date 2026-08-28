# CaseBundle案例教学契约

CaseBundle把发布案例从`released_case_dataset.json`中的嵌套记录，冻结为可版本化、可按阶段投影、可绑定Evidence/Rubric和可进入LearningEvent的案例对象。

当前发布规模：3个CaseBundle、9条受治理刑法Evidence、6个阶段包/案例。

## 三类案例标识

每个案例同时保留：

- `case_bundle_id`：由原案ID与本地权威来源SHA稳定生成，不随界面排序变化；
- `runtime_case_id`：现有FSM、sandbox目录和历史事件使用的`case_1/2/3`；
- `original_case_id`：发布数据集中的原案ID。

当前真实映射为：

| 运行ID | 原案ID | 案例 |
|---|---:|---|
| `case_1` | 1 | 指导性案例268号严某聪案 |
| `case_2` | 3 | 指导案例14号董某某、宋某某抢劫案 |
| `case_3` | 2 | 指导案例144号张那木拉正当防卫案 |

种子构建按案由轮转排序，运行ID并不等于原案ID。CaseBundle之前，教学评分器把`case_2/3`数字直接当原案ID，存在参考材料错位风险；现已统一通过runtime→bundle→original映射取教师参考。

## Schema与数据

- Schema：`schemas/case-bundle-v1.schema.json`
- CaseBundle：`dataset/case_bundles.jsonl`
- 案例Evidence：`dataset/case_bundle_evidence.jsonl`
- Manifest：`dataset/case_bundle_manifest.json`
- 构建器：`backend/scripts/build_case_bundles.py`

CaseBundle包含：来源与发布状态、稳定知识点和版本、法条Evidence ID、学生初始简报、LC/INV/PR/DS/CR/CRA阶段包、阶段能力Rubric、教师参考、典型错误、最终裁判参考、内容哈希、法源/数据集哈希和每学期复核风险。

9条案例Evidence复用`evidence-pack-item-v1`，全部从当前813条受治理法源精确解析。自由文本“以原判为准”不能转成确定法条，保留为`unresolved_legal_basis_fragments`并强制教师复核，不制造条号。

## 学生与教师投影

公开API：

- `GET /api/case-bundles/catalog`
- `GET /api/case-bundles/{runtime_or_bundle_id}`
- `GET /api/case-bundles/{id}?stage=LC|INV|PR|DS|CR|CRA`

无stage时只返回目录信息、学生简报、来源和法条Evidence；有stage时只额外返回该阶段`student_visible`与能力Rubric。公开投影明确删除：

- `reference_private`
- `teacher_reference_private`
- `typical_errors_private`
- 指导要点、参考判决、法院意见、辩护提示和预期答案

教师通过`GET /api/teacher/case-bundles/{id}`读取完整教师投影，并可在内容复核台账对`case_bundle`写`approve/request_revision/reject`事件。审核仍是不可变overlay，不直接改写bundle。

## 阶段可见性

| 阶段 | 学生可见 | 教师/评分私有 |
|---|---|---|
| LC | 案情摘要、当事人角色、初始问题 | 完整背景、事实收集重点 |
| INV | 涉嫌罪名、强制措施、羁押/取保状态 | 取保关键事实、律师预期动作 |
| PR | 起诉摘要、证据目录、量刑因素 | 辩护机会、不起诉论证 |
| DS | 认可/争议事实、量刑事实 | 辩护层级、指导要点、辩护提示 |
| CR | 公诉主张、争点、质证点 | 参考判决、法院认定/意见、指导要点 |
| CRA | 一审结论摘要、上诉理由 | 二审审查理由与最终裁判参考 |

没有二审的case_2，其CRA阶段标为`not_applicable`，不会伪造二审材料。

## LearningEvent版本绑定

案例阶段评分现在写入：

- `case_bundle_id`
- `case_bundle_version`
- `case_bundle_content_sha256`
- `law_corpus_manifest_sha256`
- `rubric_version`

事件ID也包含CaseBundle内容版本。同一学生、阶段和回答在案例版本变化后会形成新事件，不会与旧版本静默去重。adaptive投递保留这些字段，便于画像和实验按版本审计。

## Seed与运行时

`build_seed_data_criminal.py`与CaseBundle构建器共用唯一`select_diverse_cases`算法。每个sandbox seed配置显式保存原案ID、bundle ID、版本和哈希；DataLoader优先使用`original_case_id`，不再依赖当事人姓名兜底纠错。

重建顺序：

```powershell
uv run --isolated --with-requirements requirements.lock.txt -- python -X utf8 `
  backend\scripts\build_case_bundles.py

uv run --isolated --with-requirements requirements.lock.txt -- python -X utf8 `
  backend\scripts\build_seed_data_criminal.py --max-cases 3
```

构建器会拒绝：未通过案例发布门禁、未知知识ID、受治理法源缺条、绝对本地来源路径、Schema错误或seed/runtime映射漂移。

## 当前边界

- 3案仍是低风险试用案例，每学期需真实法学教师复核；
- 教师参考不是跨院校金标，争议观点不得自动定论；
- 当前Evidence只有刑法条文，尚未统一司法解释、案例原文片段和教材观点；
- CaseBundle版本绑定修复评分可审计性，不证明Agent教学效果或路径学习增益。
