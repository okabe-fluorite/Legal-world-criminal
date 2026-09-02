# LEGALWORLD 刑法版（纯刑事）

此项目是 [LEGALWORLD](https://github.com/chidaic/Legal-world.git) 的**纯刑事适配版本**——刑事公诉案件全流程 AI 仿真教学环境（委托洽谈 → 侦查 → 审查起诉 → 辩护词 → 一审 → 上诉 → 二审 → 终审）。

学生在通过发布门禁的刑事案件中扮演辩护律师，AI 扮演检察官/法官/当事人对抗；每次发言即时核验法条引用，阶段结束后按 8 能力框架提供形成性反馈，跨案件累计证据画像并沉淀补弱技能卡。当前发布集有3个机器门禁通过的低风险试用案例，仍要求法学教师每学期上线前复核；旧124案仅保留为污染修复池，不是教师金标，也不会默认展示给学生。

本项目已移除全部民事流程（起诉状/答辩状/民事一审二审/民事上诉等），仅保留刑事公诉流程与通用基础设施（法条检索、记忆工具、前台接待、地图编排等）。

## 教学能力

- **玩家辩护律师模式**：学生全程扮演辩护律师，六阶段（LC/INV/PR/DS/CR/CRA）完整走完
- **即时法条核验**：发言中的《刑法》《刑诉法》引用当场校验（条号存在性 + BM25 相近法条建议）
- **NLI 引用对齐**：CitaLaw 式三段论评估——验证"所引法条是否真的支撑该论断"（本地中文 cross-encoder + LLM 裁判双层裁决）
- **8 能力自动批阅**：CJ-Bench 刑法化框架（事实识别/规范检索/要件涵摄/主张构建/证据组织/质证对抗/立场一致/程序合规），其中规范检索为确定性公式分（可审计），其余 LLM-as-judge
- **三层学习报告**：即时警示 chip → 阶段批阅抽屉（能力横条/涵摄三栏表/引用对齐明细）→ 学期雷达档案（成长曲线/知识缺口/练习推荐）
- **技能卡闭环**：批阅发现的弱点自动沉淀为个人技能卡，下一局可查看并携带上场
- **辩护效果真实反馈**：审查起诉阶段辩护意见成立可促成不起诉提前结案；服判案件判决生效即结案

详见 `AGENTS.md`。

## 本机安装与验证

推荐直接本地启动完整效果，不需要Docker：

```powershell
# 首次使用：复制模板，在本地 .env 填写模型、SiliconFlow和讯飞配置
Copy-Item .env.example .env

# 后续直接从仓库 .env 启动
uv run --isolated --with-requirements requirements.lock.txt -- `
  python start.py
```

启动器直接读取本地`.env`，启动SQLite、backend、adaptive与Vite前端。当前演示环境使用火山引擎Ark的OpenAI兼容端点作为基线，DeepSeek官方API作为明确额度耗尽或其他瞬态故障的回退；普通401无效密钥、400和模型名错误不会被静默掩盖。密钥不打印、不提交仓库；访问`http://127.0.0.1:5173`，按`Ctrl+C`停止。

本地SQLite启用WAL和30秒busy timeout；密码哈希在写事务前完成，短注册事务仅对`database is locked`做有界退避；sandbox记录先提交再初始化seed文件。学生与教师同时首次注册/建sandbox已通过真实并发浏览器门禁，不需要为本地试用换Docker/PostgreSQL。

首次运行会自动执行一次`npm ci`。也可增加`--no-frontend`或`--no-adaptive`只启动部分服务。

前端与可复现浏览器冒烟建议使用Node.js 20或更高版本；`playwright-core`只复用本机Edge/Chrome，不下载浏览器。

本地测试：

```powershell
# 从仓库模板复制后手工填写本地配置
Copy-Item .env.example .env
uv venv .venv --python 3.11
uv pip install --python .venv\Scripts\python.exe -r requirements.lock.txt
$env:PYTHONPATH="$PWD\backend"
.venv\Scripts\python.exe backend\scripts\verify_criminal.py
.venv\Scripts\python.exe -m unittest discover -s backend\tests -v
```

`requirements.lock.txt`是跨Windows/Linux生成的冻结依赖。修改
`requirements.txt`后应重新执行：

```powershell
uv pip compile requirements.txt --universal --python-version 3.11 `
  --output-file requirements.lock.txt
```

不要提交`.env`。API Key只通过环境变量或部署密钥管理注入。

## Docker Compose生产运行（可选）

```powershell
Copy-Item .env.example .env
# 修改.env中的数据库密码、DATABASE_URL、至少32字节JWT_SECRET和模型配置
docker compose -f backend\docker-compose.yml config --quiet
docker compose -f backend\docker-compose.yml up --build
```

Compose包含PostgreSQL、后端、自适应服务和Nginx前端。前端容器代理`/api`与`/ws`，默认访问`http://127.0.0.1:5173`。`.env`只作为容器环境变量来源，不挂载进容器文件系统；不要提交该文件。

## 主模型、微调小模型与自适应服务

- 主模型优先使用`SIMLAW_PRIMARY_MODEL_*`配置，也兼容旧`OPENAI_*`；当前本地演示选择火山引擎Ark。
- `SIMLAW_FALLBACK_MODEL_*`配置DeepSeek官方API；仅明确额度耗尽或其他瞬态错误自动回退并共享熔断。
- 微调/本地小模型通过统一Model Adapter按任务灰度接入，不需要修改Agent业务代码。
- `GET /api/model/catalog`可查看脱敏路由状态。
- 精学模块产出`learning-event-v2`，先幂等写入数据库，再可选推送EduBrain自适应服务。
- `POST /api/adaptive/recommend`优先调用外部自适应服务；未配置时明确返回
  `local_evidence_heuristic`降级结果，不冒充ORCDF。

模型配置和验收边界见[`docs/MODEL_ADAPTER.md`](docs/MODEL_ADAPTER.md)。
真实六阶段链路证据见[`docs/REAL_E2E_AUDIT.md`](docs/REAL_E2E_AUDIT.md)。

## 受治理法条库

离线法条库共813条：刑法505条（2020官方正文精确合并修正案十二，形成自2024-03-01施行的现行版本）与刑诉法308条（2018第三次修正）。来源批次、原件SHA、输出SHA、版本和隔离源记录在`backend/legal_corpus/processed/law_corpus_manifest.json`。旧PDF语料漏掉刑法第二百条；某份带第三方署名且存在内容污染/差异的“2024最新版”参考件已隔离，不能覆盖生产语料，隔离理由是具体文件质量而非年份。重建与每学期复核要求见[`docs/DATA_GOVERNANCE.md`](docs/DATA_GOVERNANCE.md)。

外部`laws`目录已建立只读文件级治理库存：4,173个混合文件全部计算SHA并按原始文档/派生文本/归档/运维/缓存分层；813条正式法源不会被候选量替代。围绕10知识点和3案例筛出20个司法解释、27个案例待审候选，均未提升为正式Evidence。产物与16:9技术图见[`data_governance/DATASET_CARD.md`](data_governance/DATASET_CARD.md)和[`data_governance/DATA_GOVERNANCE_FLOW.svg`](data_governance/DATA_GOVERNANCE_FLOW.svg)。

## 受治理课程内容与EvidencePack

当前课程内容已冻结为10个KnowledgeCard、30个TaskItem、22个Evidence目录项和30条Q边。30道题的法条引用已从旧第三方路径重绑到上述受治理刑法快照；公开任务与adaptive推荐不会返回`answer_private`、`rationale_private`或`misconceptions_private`。

后端提供课程目录、公开任务、证据检索和引用审计API：

- `GET /api/knowledge/catalog`
- `GET /api/knowledge/tasks/{task_id}`
- `POST /api/knowledge/search`
- `POST /api/knowledge/audit-citations`

EvidencePack中的检索相关性和coverage只是待语义审核候选，不等于法条支持某个法律论断。三个Schema、答案隔离和构建规则见[`docs/KNOWLEDGE_CONTRACTS.md`](docs/KNOWLEDGE_CONTRACTS.md)。

全库Hybrid RAG已完成真实构建和运行时接入：2,024个法律/行政法规/司法文件/案例候选形成54,463个检索块；案例采用整案→1,591个语义父段→1,599个检索子块；JEC-QA教材形成1,404个解释块；1,184道公开题用于相似题检索，私有答案层明确不做Embedding。三库共57,051条1024维float16向量和对应SQLite词法索引，运行时为`BM25F + Qwen3-Embedding-8B → RRF → 精确条号/弃权保护 → Qwen3-Reranker-8B`。Embedding失败降级BM25F，Reranker失败降级保护后的RRF；案例命中子块后回填语义父段。120条自动候选qrels上的最终候选Recall@5为0.86、无答案误返回率为0，但教师复核仍为0，不能称正式检索准确率。报告见[`docs/HYBRID_RAG_INDEX_V1_REPORT.md`](docs/HYBRID_RAG_INDEX_V1_REPORT.md)、[`docs/HYBRID_RAG_ABLATION_V1.md`](docs/HYBRID_RAG_ABLATION_V1.md)和[`docs/HYBRID_RAG_SILICONFLOW_PROBE.md`](docs/HYBRID_RAG_SILICONFLOW_PROBE.md)。

## 预习与复习服务端闭环

登录学生现在可以通过`POST /api/adaptive/attempts`完成推荐TaskItem：adaptive服务私有判分，生成不可变`task_attempt_assessment`，backend持久化事件、画像与推荐，然后返回形成性反馈和下一任务。相同`attempt_id`重试幂等，同ID改payload返回409；旧`content_version`被拒绝，已完成任务默认从后续推荐排除。

`POST /api/adaptive/confusions`生成独立`confusion_annotation`。困惑是学生自报与教师聚合信号，不会冒充答错证据或直接降低掌握状态。推荐/题目接口始终无答案，正确选项和解析只在服务端判分后返回给当前登录学生。契约、示例、三次证据/两道任务门槛和正式考试边界见[`docs/TASK_ATTEMPT_CONTRACTS.md`](docs/TASK_ATTEMPT_CONTRACTS.md)。

登录后点击顶部“自主学习”即可进入学生连续旅程：10个知识卷宗、课程目标与法源索引、个性化任务、作答把握、服务端判分、误概念反馈、证据账本、困惑便笺和下一任务在同一页面闭环。课前以“带着问题进入课堂”的暖色问题单为主，课后以“用证据完成一次复盘”的冷色证据台为主；两者共享TaskAttempt契约但不混淆学习目的。桌面为三栏卷宗，窄屏改为单列并保留困惑入口。页面形态与可复现浏览器冒烟见[`docs/STUDENT_LEARNING_JOURNEY.md`](docs/STUDENT_LEARNING_JOURNEY.md)。

顶部“认知诊断”是比赛展示核心页：在线Evidence-KT保守画像与学生事件时间线、ORCDF V0/V1/V2真实shadow实验、选择/短答/案件/角色互换七步路径和四任务Model Adapter路由集中展示。ORCDF明确来自MOOCCubeX民法/宪法、mastery未校准且不进入当前刑法学生画像；微调未连接时显示`not_connected`。展示口径、来源SHA和浏览器脚本见[`docs/COGNITIVE_DIAGNOSIS_SHOWCASE.md`](docs/COGNITIVE_DIAGNOSIS_SHOWCASE.md)。

认知驾驶舱同时提供真实KnowledgeCard先修图、法律论证脚手架和“多模态 / 数字人”能力页：10个知识节点/10条先修边不使用LLM补边；私有音频/图片上传会做JWT隔离、类型/大小检查和SHA-256；配置讯飞凭据后，浏览器可通过AudioWorklet实时PCM→IAT partial/final→受治理Evidence回复→TTS自动播放，页面显示真实输入电平和设备名；无凭据时显示`not_configured`，有凭据但未完成本轮真实调用时显示`configured_not_verified`。ASR结果保持`needs_review`且不生成LearningEvent，视觉和数字人继续`not_connected`，浏览器`SpeechSynthesis`只作fallback。完整API、讯飞/Azure/LiveKit选型和证据边界见[`docs/MULTIMODAL_AVATAR_ARCHITECTURE.md`](docs/MULTIMODAL_AVATAR_ARCHITECTURE.md)，说明书逐项状态见[`docs/PRODUCT_SPEC_IMPLEMENTATION_MATRIX_V2.md`](docs/PRODUCT_SPEC_IMPLEMENTATION_MATRIX_V2.md)，上游代码级对照见[`docs/UPSTREAM_LEGALWORLD_COMPARISON.md`](docs/UPSTREAM_LEGALWORLD_COMPARISON.md)。

顶部“可信RAG”对应赛题内容质量要求：罪刑法定/从旧兼从轻、特殊防卫、抢劫罪构成3题均展示AI回答、标准答案、权威法条/指导案例、版本/时效、实际引用和关键要点；错误条号或伪造引文可现场检查。普通界面不展示SHA、内部Evidence ID或机器状态码；当前3题引用检查通过，但法学专家复核仍待完成，不能写成专家确认准确率。报告见[`docs/TYPICAL_QUESTION_EVALUATION.md`](docs/TYPICAL_QUESTION_EVALUATION.md)，复跑命令为`python backend/scripts/run_typical_question_evaluation.py --live-model --model-config <path>`，免模型复审可用`--reuse-report`。

困惑入账后可进入“AI分层解惑”：系统先提出诊断追问，学生说明自己的理解后，才返回规范原文、白话解释、事实适用、争议边界和下一动作。模型引用必须来自当前KnowledgeCard标准Evidence并通过条号/逐字片段门禁；失败自动使用确定性fallback，低置信度标记教师复核。解惑不计分、不生成LearningEvent、不更新长期掌握，详见[`docs/GOVERNED_LEARNING_SUPPORT.md`](docs/GOVERNED_LEARNING_SUPPORT.md)。

同一自主学习卷宗现提供13个主观任务：10个知识点短答和3个CaseBundle角色互换。模型任务`subjective_scoring`只形成修改建议，低置信度、坏结构、学生引用失败或越界Evidence均弃权；高置信度也必须进入任课教师匿名复核队列。只有教师批准并给出0—1分与`mastered/partial/missing`判定后，才生成`teacher_reviewed_subjective_assessment`进入画像；退回/拒绝不入画像。学生可在“我的复核台账”查看教师结论，退回稿一键带入原文修订；同一稿件只允许一次教师决定和一次画像事件。契约、API、真实浏览器闭环与证据边界见[`docs/SUBJECTIVE_TASK_REVIEW.md`](docs/SUBJECTIVE_TASK_REVIEW.md)。

显式授予teacher/admin角色后，顶部会出现“教师驾驶舱”：教师可建立自己的班级、加入已注册学生、查看匿名形成性学情，对3个CaseBundle、10个KnowledgeCard和30个TaskItem写不可变内容复核事件，并复核自有班级的主观稿件。普通注册不能自报教师；班级聚合不含学生邮箱、困惑原文或排行榜，少于默认3人时抑制知识/能力/错误细分，内容审核也不会绕过冻结源文件。角色授权、API和本地教师冒烟见[`docs/TEACHER_MINIMUM_LOOP.md`](docs/TEACHER_MINIMUM_LOOP.md)。

## 产品机制审计与课堂试点

不调用网络、LLM或课堂数据即可复跑产品机制审计：

```powershell
uv run --isolated --with-requirements requirements.lock.txt -- python -X utf8 `
  backend\scripts\run_product_evidence_audit.py
```

当前结果：10个课程查询纯BM25 expected-hit@5为90%，绑定KnowledgeCard标准Evidence后为100%；22条Evidence条号/逐字片段22/22；missing/困惑信号均使10/10目标知识点排到第1，平均前移4.5位；已答排除、答案隔离、模型目录脱敏通过。新增主观任务门禁也已通过：13题公开私有字段0、高置信度仍不直接入画像、坏Evidence弃权、教师批准后才生成1条合格事件。完整JSON/摘要见[`docs/PRODUCT_EVIDENCE_AUDIT.md`](docs/PRODUCT_EVIDENCE_AUDIT.md)。这些是软件机制证据，不是法律蕴含、掌握校准、学习增益或路径因果效果。

证据分级与后续Agent/真实模型消融条件见[`docs/ABLATION_PROTOCOL.md`](docs/ABLATION_PROTOCOL.md)；8—12人只做可行性试点，方案见[`docs/CLASSROOM_PILOT_PROTOCOL.md`](docs/CLASSROOM_PILOT_PROTOCOL.md)。50人试用必须等待院校授权、有效法复核、隐私/伦理流程和预注册实验设计。

## 案例发布边界

产品默认只读取`dataset/released_case_dataset.json`，旧124案保留为污染数据修复池，
不会直接展示给学生。重新生成seed前必须通过：

```powershell
uv run --no-project --python 3.11 --with-requirements requirements.lock.txt `
  python backend\scripts\audit_case_dataset.py `
  --dataset dataset\released_case_dataset.json `
  --require-all-releasable
```

治理规则见[`docs/DATA_GOVERNANCE.md`](docs/DATA_GOVERNANCE.md)。

3个发布案例现已进一步冻结为CaseBundle：稳定bundle ID、运行ID/原案ID映射、9条受治理刑法Evidence、六阶段学生可见材料、教师参考、能力Rubric、典型错误和内容版本统一记录。案例选择卡会显示bundle版本、Evidence数量和教师复核标记；公开阶段API不返回指导要点、参考判决或教师预期答案。

CaseBundle还修复了一个真实映射问题：种子按案由排序后，`case_2→原案3`、`case_3→原案2`，评分器此前可能按数字取错参考材料。现在sandbox配置和LearningEvent均绑定bundle ID/版本/哈希、原案ID、法源manifest和Rubric版本。完整契约及重建顺序见[`docs/CASE_BUNDLE_CONTRACT.md`](docs/CASE_BUNDLE_CONTRACT.md)。

## 刑事流程

```
接受委托 → 侦查阶段 → 审查起诉 → 辩护词起草 → 刑事一审 → 上诉决策 → 刑事二审 → 终审
    LC        INV         PR          DS          CR         CRA
```

### 阶段码

| 阶段码 | 名称 | 说明 |
|--------|------|------|
| LC | 委托洽谈 | 律师与委托人家属洽谈，建立委托关系 |
| INV | 侦查阶段 | 律师会见嫌疑人、了解涉嫌罪名、申请取保候审 |
| PR | 审查起诉阶段 | 阅卷、会见被告人、向检察官提交辩护意见 |
| DS | 辩护词起草 | 收到起诉书后起草《辩护词》 |
| CR | 刑事一审庭审 | 公诉人 vs 辩护人对抗式庭审 |
| CRA | 刑事二审庭审 | 上诉后的二审终审 |

### 角色

| 角色 | 说明 |
|------|------|
| 委托人（家属） | 刑事案由家属启动，代为委托辩护律师 |
| 被告人 | 犯罪嫌疑人/被告人 |
| 辩护律师 | 维护被告人合法权益 |
| 检察官 | 国家公诉人 |
| 侦查人员 | 公安侦查员（可选） |
| 法官 | 刑事审判长 |

### 刑事特有程序

- 取保候审申请（侦查阶段）
- 非法证据排除（庭审质证）
- 认罪认罚从宽（审查起诉阶段）
- 被告人最后陈述（一审庭审）
- 上诉/抗诉（一审判决后）
- 不起诉提前结案（审查起诉阶段，辩护成功）

## 目录结构

```
Legal-world-criminal/
├── README.md
├── requirements.txt
├── start.py
├── dataset/                       # 刑事案例数据集
├── dataset_builder/               # 数据集构建工具
├── docs/
├── examples/
└── backend/
    ├── ws_server.py               # WebSocket 入口
    ├── sandbox_main.py
    ├── scripts/                   # 数据准备、迁移、验证脚本
    ├── legal-skillhub/
    │   └── public/legal/
    │       ├── client/memory/     # 当事人记忆
    │       └── lawyer/
    │           ├── memory/        # 律师记忆
    │           └── document-drafting/
    │               ├── lawyer-defense-opinion-drafting/   # ★ 刑事辩护词
    │               └── lawyer-criminal-appeal-drafting/   # ★ 刑事上诉状
    └── src/
        ├── agents/
        │   ├── base_agent.py
        │   ├── receptionist_agent.py    # 前台
        │   ├── client_agent.py          # 当事人
        │   ├── lawyer_agent.py          # 辩护律师
        │   ├── judge_agent.py           # 刑事法官
        │   ├── prosecutor_agent.py      # ★ 检察官/公诉人
        │   └── investigator_agent.py    # ★ 公安侦查员（可选）
        ├── scenarios/
        │   ├── base_scenario.py
        │   ├── legal_consultation.py    # 委托洽谈（刑事入口）
        │   ├── investigation.py         # ★ 侦查阶段
        │   ├── prosecution_review.py    # ★ 审查起诉阶段
        │   ├── defense_opinion_drafting.py  # ★ 辩护词起草
        │   ├── criminal_trial.py        # ★ 刑事一审
        │   └── criminal_appeal_trial.py # ★ 刑事二审
        ├── tools/
        │   ├── common/             # 通用工具（法条检索、技能加载等）
        │   ├── client/             # 当事人记忆工具
        │   └── legal/              # 刑事文书工具（起诉书/辩护词/公诉词/刑一刑二判决书）
        ├── pipeline/               # 阶段→工具分配（纯刑事 manifest）
        ├── orchestration/          # 状态机 / 编排引擎
        ├── player_lawyer/          # 玩家扮演辩护律师
        └── teaching/               # ★ 教学评分（8能力/引用核验/NLI对齐/画像/技能卡）
```

## 验证

```bash
cd backend
python scripts/verify_criminal.py
```

## 许可

本项目基于原始 [LEGALWORLD](https://github.com/chidaic/Legal-world.git) 项目，遵循相同的开源许可协议。
