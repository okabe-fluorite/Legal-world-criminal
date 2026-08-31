# 星火智学完整产品说明书逐项实现矩阵 V2

- 基准：`星火智学_完整产品形态与系统架构说明书_V1.0(3).docx`
- 上游：`sii-research/Legal-world@979ee9619f187d227059316f849c17ecc530c816`
当前仓库审计日期：2026-08-30

状态只使用：`implemented`、`implemented_with_boundary`、`interface_reserved`、`external_provider_required`、`deferred`、`not_recommended`。

## 产品旅程与教学闭环

| 产品要求 | 说明书证据 | 上游实现 | 当前实现与代码证据 | 状态 | 仍有缺口/边界 | 本轮动作 |
|---|---|---|---|---|---|---|
| 本科刑法预习—精学—复习—教师闭环 | §1、§2.2、§3 | 无课堂闭环 | `LearningJourney.vue`、案件工作台、TaskAttempt、TeacherDashboard | `implemented_with_boundary` | 无真实课堂学习增益证据 | 保持主线，不伪造试用 |
| 课程知识地图 | §3.2 | 无 | 10张KnowledgeCard + 本轮真实先修DAG SVG | `implemented` | 仅首批刑法模块 | 新增10节点/10边知识图 |
| 强制困惑标注 | §3.2、§7.1 | 无 | 困惑便笺、幂等自报事件和教师聚合 | `implemented_with_boundary` | 当前不强制每次预习填写 | 保持自愿，避免形式化垃圾数据 |
| AI先追问再分层解惑 | §3.2 | 无 | `learning_support`两步会话、Evidence门禁与fallback | `implemented_with_boundary` | 教师复核队列和效果证据待补 | 无需改动 |
| 预习选择/微型案例/主观题 | §3.2 | 无 | 30选择题、10短答、3角色互换 | `implemented_with_boundary` | 主观题无真实难度/区分度 | 无需新增伪参数 |
| 案件调查与信息权限 | §3.3、§7.2 | 有民事阶段/工具思想 | 六阶段刑事FSM、stage tool manifest、3个CaseBundle | `implemented` | 仅3个发布案例 | 上游仅作抽象对照 |
| AI对抗辩手主动质询 | §3.3、§5.3 | 有Agent对话 | 庭审对抗存在 | `implemented_with_boundary` | 主动漏洞追问仍可增强 | 后置，当前视频已有多智能体证据 |
| 法源核验与Rubric反馈 | §3.3 | citation/tool接口 | 四层评分、引用检查、NLI、8能力Rubric | `implemented_with_boundary` | 主观争议仍需教师 | 保持形成性评价 |
| 错因分类与复习 | §3.4 | 无 | 错误标签、技能卡、下一任务 | `implemented_with_boundary` | 间隔时间衰减未正式实现 | 保留当前重排逻辑 |
| 变式与角色互换 | §3.4 | 民事上诉/文书变式可参考 | 3个角色互换SubjectiveTask | `implemented_with_boundary` | 只覆盖3案 | 不盲目扩题 |
| 语音快问快答 | §3.4、§5.6 P1 | 无 | 浏览器AudioWorklet实时PCM→讯飞IAT partial/final→Evidence短答→TTS自动播放；浏览器朗读fallback | `implemented_with_boundary` | 已验证多轮协议，真实课堂多说话人准确率与教师转写复核仍待试点 | 主交互升级为实时语音 |
| 教师内容审核 | §3.5 | 人评工具但非课堂教师端 | 不可变review overlay、案例/卡/任务审核 | `implemented_with_boundary` | 无内容在线修订/下线工作流 | 保持冻结内容+overlay |
| 班级匿名学情 | §3.5 | 无 | 班级、选课、最小人数抑制、知识/能力/错误/困惑聚合 | `implemented_with_boundary` | 无教务同步和多教师 | 比赛后置 |
| 主观题教师门禁 | §1.4、§3.5 | 无 | approve/revision/reject、修订带回、一次决定一次事件 | `implemented_with_boundary` | 无双评/仲裁/正式成绩 | 已完成，不扩正式考试 |

## 核心技术与七对象

| 产品要求 | 说明书证据 | 上游实现 | 当前实现与代码证据 | 状态 | 仍有缺口/边界 | 本轮动作 |
|---|---|---|---|---|---|---|
| KnowledgeCard | §5.1、§6.1 | 无课程对象 | 10卡、版本/哈希/法源/先修/易错点 | `implemented` | 覆盖范围小 | 本轮可视化DAG |
| CaseBundle | §6.1 | 案例数据与场景配置 | 3个稳定bundle、六阶段投影、Evidence/Rubric | `implemented_with_boundary` | 待本学期教师复核 | 保持边界 |
| TaskItem/SubjectiveTask | §6.1 | 咨询问题构建器 | 30选择+13主观契约 | `implemented_with_boundary` | 无真实题目参数 | 不伪造参数 |
| EvidencePack | §5.2、§6.1 | 可选法条检索/citation | 受治理BM25、效力/版本/片段/风险/审计 | `implemented_with_boundary` | coverage不是语义蕴含 | 保持候选状态 |
| LearningEvent | §6.1 | 无课堂事件 | 不可变事件、版本、幂等和资格门禁 | `implemented_with_boundary` | 部分案件耗时/模型版本不完整 | 媒体事件明确不创建 |
| LearnerProfile | §5.4、§6.1 | 无 | Evidence-KT在线画像、事件门槛、错误/困惑 | `implemented_with_boundary` | 非校准概率、无充分课堂数据 | ORCDF继续shadow |
| Recommendation | §5.4、§6.1 | 无 | 规则候选、先修回退、七步路径、原因码 | `implemented_with_boundary` | 非因果最优、间隔调度有限 | 保持诚实说明 |
| 可信RAG与引用审查 | §5.2 | 工具接口可参考 | 三典型题、错误引用拒绝、法源版本/SHA | `implemented_with_boundary` | 专家结论仍pending | 无需改动 |
| 混合/向量/图检索 | §5.2 | 可选向量索引 | BM25 + 轻量先修图；向量可插拔 | `implemented_with_boundary` | 未启用向量不影响P0 | 不引入未治理远程向量 |
| 智能体显式状态机 | §5.3、§7.2 | 核心参考来源 | 刑事六阶段FSM、Agent/Tool分离 | `implemented` | 未换LangGraph | 现有显式FSM足够，不为技术名重写 |
| Model Adapter | §5.5 | 模型配置/运行层 | 任务路由、fallback、small-model not_connected | `implemented_with_boundary` | 无正式LoRA/SFT | 保持接口和真实状态 |
| 模型微调对比 | §5.5、§10.1 | 无本项目微调结果 | 对比接口和协议存在 | `interface_reserved` | 训练、模型卡、独立评测未完成 | 不伪造微调 |
| ORCDF/旧EduBrain适配 | §5.4、§9 P1 | 无 | V0/V1/V2真实实验、47题对照、shadow面板 | `implemented_with_boundary` | 民法/宪法迁移，不是刑法课堂 | 保持隔离 |
| 课程知识图 | §5.6 P1 | 无 | 10节点、10条真实先修关系，不用LLM补边 | `implemented` | 首批课程范围 | 本轮新增 |
| 法律论证图 | §5.6 P1、§7.2 | 无 | 争点→事实→证据→主张→质询→门禁模板 | `implemented_with_boundary` | 当前是模板，不是学生已提交图 | 本轮新增并显著标界 |
| 显式证据板 | §5.6 P0 | 工具/文书输出可参考 | RAG证据、CaseBundle、引用面板可见 | `implemented_with_boundary` | 尚无自由拖拽证据—主张编辑器 | 不为3分钟视频扩复杂编辑器 |

## 多模态、数字人与平台能力

| 产品要求 | 说明书证据 | 上游实现 | 当前实现与代码证据 | 状态 | 仍有缺口/边界 | 本轮动作 |
|---|---|---|---|---|---|---|
| 流式文本/案件工作台 | §5.6 P0 | WebSocket | Vue工作台、WebSocket事件 | `implemented` | — | 无需改动 |
| 私有媒体资产 | §5.6 P1隐含 | 无 | `media_assets`、JWT、SHA、类型/大小门禁 | `implemented` | 无内容病毒扫描 | 本轮新增 |
| ASR | §5.6 P1 | 无 | `/ws/realtime-voice`实时讯飞IAT；`/api/multimodal/transcriptions`文件兼容 | `implemented_with_boundary` | ASR固定needs_review；faster-whisper未实现 | 真实桌面/窄屏/视频段验收 |
| 图像理解/OCR | §5.6 P1多模态 | 无 | `/api/multimodal/visual-analyses` | `interface_reserved` | Provider未选 | 本轮冻结契约 |
| 服务端TTS | §5.6 P1 | 无 | 讯飞在线TTS真实适配器；实时回复WAV回传自动播放；`/api/speech/synthesis`私有资产兼容 | `implemented_with_boundary` | 云配额/网络依赖；不形成学习证据 | 真实音频和多轮播放验收 |
| 浏览器本地朗读 | §5.6 P1降级 | 无 | CognitiveDashboard SpeechSynthesis | `implemented_with_boundary` | 无下载资产、浏览器依赖 | 本轮新增真实fallback |
| 数字人 | §5.6 P2、§9 P2 | 无 | `/api/avatar/renders`、AI标识和肖像同意门禁 | `external_provider_required` | 需讯飞/Azure授权、费用和适配器 | 本轮只预留，不宣称完成 |
| 简单动画/复杂立绘 | §5.6 P2 | 小镇角色与静态素材 | 现有2D角色/阶段背景 | `implemented_with_boundary` | 不是数字人/3D | 不继续扩美术 |
| 自动视频 | §5.6 P2 | 无 | 比赛视频构建脚本和162.2秒技术主线DRAFT，含讯飞实时语音段，非产品能力 | `implemented_with_boundary` | 仍需真实人员完整审片 | 机器审片包已重建 |
| WebRTC房间/全双工语音 | 技术演进项 | 无 | 当前已实现PCM WebSocket半双工多轮；LiveKit/WebRTC房间未接入 | `deferred` | 多人、打断、TURN与弱网治理待Beta | Beta后评估 |

## 治理、评测、部署与范围

| 产品要求 | 说明书证据 | 上游实现 | 当前实现与代码证据 | 状态 | 仍有缺口/边界 | 本轮动作 |
|---|---|---|---|---|---|---|
| 全链路版本和AI标识 | §5.7 | 部分trace/version | 法源/案例/任务/Prompt/模型路由多处绑定 | `implemented_with_boundary` | 无统一单页成本追踪 | 媒体补AI标识与哈希 |
| 隐私和权限 | §5.7、§8.3 | 用户/sandbox | JWT、角色、匿名聚合、私有资产、公开包扫描 | `implemented_with_boundary` | 非正式校园合规评估 | 本轮新增媒体跨用户404 |
| 实验隔离 | §5.7、§10 | 研究eval | ORCDF shadow、三题、产品机制审计、协议 | `implemented_with_boundary` | 真实课堂/Agent同条件消融未完成 | 保持未完成状态 |
| 失败降级 | §8.3、§11 | runtime strategy | 模型fallback、RAG/AI解释fallback、media not_connected | `implemented` | Provider连接后需增加熔断 | 本轮补媒体真实降级 |
| 本地可复现 | §8 | 上游推荐Docker/PostgreSQL | `start.py`、SQLite+adaptive+Vite、锁文件 | `implemented` | 文档中旧`.venv`状态曾漂移 | 本轮用uv重建并验证 |
| Docker/PostgreSQL主线 | §8建议 | 上游默认 | 当前比赛不采用 | `not_recommended` | 正式多机部署再评估 | 不投入Docker |
| 8—12人/50人用户试验 | §10.2 | 无 | 协议与材料DRAFT | `deferred` | 真实人员未完成 | 按用户要求暂缓 |
| 3典型问题准确性论证 | §12.5/赛题 | 无 | 自动门禁3/3，专家pending | `implemented_with_boundary` | 仍需真实法学专家 | 暂缓真实人员材料 |

## 本轮新增的可展示证据

- 认知驾驶舱“多模态 / 数字人”页以实时语音为主，文件上传只标为兼容/审计工具。
- 1500×980真实浏览器两轮验证：384个PCM分片、54个partial、2个final、2个Evidence回复与2段TTS；780×900单轮192分片；文件上传0、LearningEvent 0→0，控制台、页面、HTTP和请求失败均为0。
- 媒体页面明确显示ASR`needs_review`、LearningEvent/正式评分/自动画像更新均为0，数字人`not_connected`。
- 后端全量125/125通过；前端类型检查、Vite生产构建、认知驾驶舱旧路径和实时语音专用smoke均通过。
