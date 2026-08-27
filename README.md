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
uv run --isolated --with-requirements requirements.lock.txt -- `
  python start.py --model-config E:\guabangjieshuai\EduBrain\.env.example
```

该命令使用本地SQLite，自动启动backend、adaptive与Vite前端；能识别三组重复的`api_key/baseurl/model`配置，正常优先OpenCode，429/用量窗口/服务暂不可用时自动回退DeepSeek官方API。密钥仅进入子进程环境，不打印、不写入仓库。访问`http://127.0.0.1:5173`，按`Ctrl+C`停止。

首次运行会自动执行一次`npm ci`。也可增加`--no-frontend`或`--no-adaptive`只启动部分服务。

前端与可复现浏览器冒烟建议使用Node.js 20或更高版本；`playwright-core`只复用本机Edge/Chrome，不下载浏览器。

本地测试：

```powershell
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

- 主模型继续使用`OPENAI_*`配置。
- 主模型可配置为OpenCode，`SIMLAW_FALLBACK_MODEL_*`配置DeepSeek官方API；仅瞬态错误自动回退并共享熔断。
- 微调/本地小模型通过统一Model Adapter按任务灰度接入，不需要修改Agent业务代码。
- `GET /api/model/catalog`可查看脱敏路由状态。
- 精学模块产出`learning-event-v2`，先幂等写入数据库，再可选推送EduBrain自适应服务。
- `POST /api/adaptive/recommend`优先调用外部自适应服务；未配置时明确返回
  `local_evidence_heuristic`降级结果，不冒充ORCDF。

模型配置和验收边界见[`docs/MODEL_ADAPTER.md`](docs/MODEL_ADAPTER.md)。
真实六阶段链路证据见[`docs/REAL_E2E_AUDIT.md`](docs/REAL_E2E_AUDIT.md)。

## 受治理法条库

离线法条库共813条：刑法505条（2020官方正文精确合并修正案十二）与刑诉法308条（2018第三次修正）。来源批次、原件SHA、输出SHA、版本和隔离源记录在`backend/legal_corpus/processed/law_corpus_manifest.json`。旧PDF语料漏掉刑法第二百条，含第三方署名的“2024最新版”也已隔离，均不得覆盖生产语料。重建与每学期复核要求见[`docs/DATA_GOVERNANCE.md`](docs/DATA_GOVERNANCE.md)。

## 受治理课程内容与EvidencePack

当前课程内容已冻结为10个KnowledgeCard、30个TaskItem、22个Evidence目录项和30条Q边。30道题的法条引用已从旧第三方路径重绑到上述受治理刑法快照；公开任务与adaptive推荐不会返回`answer_private`、`rationale_private`或`misconceptions_private`。

后端提供课程目录、公开任务、证据检索和引用审计API：

- `GET /api/knowledge/catalog`
- `GET /api/knowledge/tasks/{task_id}`
- `POST /api/knowledge/search`
- `POST /api/knowledge/audit-citations`

EvidencePack中的检索相关性和coverage只是待语义审核候选，不等于法条支持某个法律论断。三个Schema、答案隔离和构建规则见[`docs/KNOWLEDGE_CONTRACTS.md`](docs/KNOWLEDGE_CONTRACTS.md)。

## 预习与复习服务端闭环

登录学生现在可以通过`POST /api/adaptive/attempts`完成推荐TaskItem：adaptive服务私有判分，生成不可变`task_attempt_assessment`，backend持久化事件、画像与推荐，然后返回形成性反馈和下一任务。相同`attempt_id`重试幂等，同ID改payload返回409；旧`content_version`被拒绝，已完成任务默认从后续推荐排除。

`POST /api/adaptive/confusions`生成独立`confusion_annotation`。困惑是学生自报与教师聚合信号，不会冒充答错证据或直接降低掌握状态。推荐/题目接口始终无答案，正确选项和解析只在服务端判分后返回给当前登录学生。契约、示例、三次证据/两道任务门槛和正式考试边界见[`docs/TASK_ATTEMPT_CONTRACTS.md`](docs/TASK_ATTEMPT_CONTRACTS.md)。

登录后点击顶部“自主学习”即可进入学生连续旅程：10个知识卷宗、课程目标与法源索引、个性化任务、作答把握、服务端判分、误概念反馈、证据账本、困惑便笺和下一任务在同一页面闭环。桌面为三栏卷宗，窄屏改为单列并保留困惑入口。页面形态与可复现浏览器冒烟见[`docs/STUDENT_LEARNING_JOURNEY.md`](docs/STUDENT_LEARNING_JOURNEY.md)。

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
