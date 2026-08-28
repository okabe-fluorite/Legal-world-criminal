# 案例与法源治理

## 数据分层

- `dataset/criminal_case_dataset.json`：历史原始解析/增强结果，仅供审计与修复，禁止直接进入学生端。
- `dataset/legacy_case_quality_audit.json`：旧124案机器质量审计。当前124案全部因缺正式发布状态而阻断。
- `dataset/released_case_dataset.json`：正式产品只读取的案例发布集。
- `dataset/released_case_quality_audit.json`：发布集逐案门禁结果。
- `dataset/case_bundles.jsonl`：按运行ID冻结的3个案例教学包，含阶段公开/私有材料、Rubric和版本。
- `dataset/case_bundle_evidence.jsonl`：案例引用的受治理刑法Evidence目录。
- `dataset/case_bundle_manifest.json`：运行ID→bundle→原案ID映射、文件/Schema/法源哈希。
- `dataset/knowledge_catalog.json`：教师批准试用的稳定知识点ID。
- `adaptive_service/data/knowledge_cards.jsonl`：从稳定知识点扩展出的受治理课程知识卡。
- `adaptive_service/data/task_items.jsonl`：从教师批准试用题重绑官方法源后的受治理任务；含服务端私有判分字段。
- `adaptive_service/data/evidence_catalog.jsonl`：TaskItem与KnowledgeCard共用的受治理法条证据目录。

当前发布集为3案：指导性案例268号严某聪案、指导案例144号张那木拉案、指导案例14号董某某/宋某某案；机器门禁3/3通过，但仍不等于正式教师金标。

发布案例必须具有：

1. 明确的`pilot_release_approved`状态和适用边界；
2. 原始来源标题、机构、URL、本地只读来源相对路径和SHA-256；
3. 被告、案情、法院查明、罪名、判决和法条的一致性；
4. 稳定`knowledge_id`，不能使用LLM自由文本替代Q矩阵ID；
5. 机器门禁通过，并保留法学教师复核要求。

## 质量门禁

```powershell
uv run --no-project --python 3.11 --with-requirements requirements.lock.txt `
  python backend\scripts\audit_case_dataset.py `
  --dataset dataset\released_case_dataset.json `
  --source-root <只读laws目录> `
  --output dataset\released_case_quality_audit.json `
  --require-all-releasable
```

`build_seed_data_criminal.py`默认只读取发布集，并在写seed前再次执行门禁。扩充案例时先修改发布集，再运行门禁和测试；不得把旧124案整体复制回seed目录。

发布集通过后必须先运行`build_case_bundles.py`再重建seed。CaseBundle构建器复用seed选案排序，拒绝映射漂移，并将`original_case_id/case_bundle_id/version/content_sha256`写入每个case配置。学生API只返回阶段公开投影；教师参考、指导要点、参考裁判和典型错误不得进入学生投影。详见[`CASE_BUNDLE_CONTRACT.md`](CASE_BUNDLE_CONTRACT.md)。

## 法源

生产法条库现由国家法律法规数据库下载件构建：

- 刑法：2020年官方合并正文 + 官方《刑法修正案（十二）》精确合并，共505条；
- 刑诉法：2018年第三次修正官方正文，共308条；
- `backend/legal_corpus/processed/law_corpus_manifest.json`记录下载批次、原件相对路径、完整SHA-256、输出SHA-256、版本和隔离源；
- 含“中国刑事辩护网提供”的第三方“2024最新版”已隔离，不参与构建；
- 旧PDF构建结果漏掉刑法第二百条，禁止回退覆盖受治理语料。

重建命令：

```powershell
uv run --isolated --with-requirements requirements.lock.txt -- python -X utf8 `
  backend\scripts\build_law_corpus_from_official_docx.py `
  --criminal-law-docx <国家数据库刑法DOCX> `
  --amendment-12-docx <刑法修正案十二DOCX> `
  --criminal-procedure-docx <国家数据库刑诉法DOCX> `
  --source-root <只读laws目录> `
  --output-dir backend\legal_corpus\processed `
  --download-snapshot-date 2026-02-26
```

进入每学期真实课堂前仍必须：

- 对照届时有效国家法律法规数据库文本；
- 清除第三方站点污染短语；
- 记录法规版本、effective date、官方URL和源文件SHA-256；
- 重建JSONL后执行条号唯一性、关键条文逐字抽检和引用回归测试。

下载件未保存法规详情页URL，因此当前`source_url`诚实记录官方门户
`https://flk.npc.gov.cn/`，并在manifest中标记`not_preserved_in_download_artifacts`；不得伪造详情URL。

## 课程内容发布

`backend/scripts/build_governed_learning_content.py`负责把教师批准题库、Q矩阵和稳定知识点重绑到受治理法源，并生成KnowledgeCard、TaskItem和Evidence目录。构建器会拒绝法条引用片段不匹配、绝对本地路径、Schema错误或哈希漂移。

TaskItem中的`answer_private`、`rationale_private`和`misconceptions_private`只用于服务端判分；知识API和adaptive推荐必须使用公开投影。检索coverage与词法重叠只能标为待语义审核候选，不得作为法律蕴含结论或教师金标。详细契约见[`KNOWLEDGE_CONTRACTS.md`](KNOWLEDGE_CONTRACTS.md)。

TaskAttempt使用客户端ID和完整payload哈希保持不可变：同ID同payload幂等，同ID改内容冲突。backend以登录用户身份覆盖浏览器身份，并只持久化作答LearningEvent、画像与推荐，不在adaptive响应快照保存正确选项或解析。答案提前揭示的尝试只给反馈、不进入长期画像；困惑标注是自报信号，不直接降低知识状态。详见[`TASK_ATTEMPT_CONTRACTS.md`](TASK_ATTEMPT_CONTRACTS.md)。
