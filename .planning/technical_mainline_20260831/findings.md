# 技术主线发现

## 新目标变化
- 项目叙事从产品功能转为Qwen3-8B刑法学科模型方法与四场景应用验证。
- 新增四个机器可执行主任务：法学数据治理、Evidence结构化推理、LegalEduEval、Agent消融；轻量2D导师为交互增强。
- 模型训练归队友；当前继续保持OpenCode/DeepSeek基线和微调pending。

## 已确认基线
- 当前仓库HEAD与远端为`e1fd49a`，tracked工作区无修改；存在用户未跟踪PPT/素材和3份新策略文档，必须保留。
- 既有产品闭环、三案例浏览器彩排、PPT/视频/效果报告DRAFT不重复实现。
- 上一个Live2D调研计划已完成，结论为使用4张原创透明状态图的轻量2D导师，不引入Cubism主线。

## 数据边界
- 既有记忆只用于维持ORCDF/MOOCCubeX迁移边界；当前数据治理统计必须重新读取本地`laws`目录和正式corpus manifest。

## 待核验
- `laws`当前真实文件数/类型/重复组和目录结构。
- 正式813条语料、10知识点、3案例Evidence与候选L2/L3来源之间的可映射范围。
- 是否已有LegalEduEval或消融脚本可复用。
- `websdk-python-master`可复用的讯飞多模态客户端、依赖、鉴权和许可证边界。
- `D:\Code\biyesheji_jiaofu\结果测评`及用户补充的相近路径中可用于LegalEduEval的真实资产。

## 2026-08-31本地真实库存
- `laws`当前恰有4,173个文件、255,164,821字节；其中2,616 TXT、1,458 DOCX、53 DOC、30 ZIP、10 PY、2 MD、2 PYC、1 example、1 JSON。
- 新目标/旧策略中“530 DOC”不符合当前磁盘；530是`output_cases`的TXT案例数量，不是DOC数量。后续材料必须改用53 DOC。
- 顶层业务输出为：`output_laws`335、`output_regulations`610、`output_judicial`549、`output_cases`530、`output_categories`60；另有`raw_data`2041、29个原始压缩包和1个98.8MB `data.zip`。
- 4173总量混合原始文档、派生TXT、ZIP、脚本、缓存和说明文件，不能全部作为内容候选，更不能称训练样本数。库存Schema需显式区分`source_document/derived_text/archive/operational/cache`。
- 正式语料manifest确认刑法505条（截至2024-03-01）+刑诉法308条（截至2018-10-26），来源3个官方DOCX，隔离1个第三方污染刑法DOCX；输出JSONL SHA已冻结。
- 当前课程内容manifest为10 KnowledgeCard、30 TaskItem、22 Evidence、30 Q边；CaseBundle另有3案/9条案件Evidence。
- 仓库已有`docs/ABLATION_PROTOCOL.md`和软件机制审计，但明确`agent_ablation_run_in_this_audit=false`；LegalEduEval只有策略描述，没有100题数据/Schema/Runner。

## 四层映射抽查
- `raw_data`源目录实际为法律347、司法解释553、行政法规610、指导性案例530；派生输出分别335/549/610/530，说明并非所有raw文档都产生一个派生发布候选，必须保留转换失败/合并/隔离状态。
- 与10知识点直接相关的司法解释标题至少覆盖抢劫、未成年人责任、共同犯罪、故意/过失相关专题；不能仅凭标题自动晋级正式Evidence，先标`candidate_requires_legal_review`。
- 与3个CaseBundle和核心知识直接相关的案例可明确找到指导案例144号、检例45—48号正当防卫系列、指导案例14号/检例17/19/20/23/103号抢劫系列等；案例来源中包含北大法宝批量包，版权/再分发边界需要单独记录，不能等同国家官方法源。
- KnowledgeCard当前10个稳定ID及条号映射可作为`knowledge_evidence_links`唯一知识端锚点；正式L1链接来自22条课程Evidence，L2/L3只生成待教师审核候选。

## 用户补充参考审计
### 讯飞websdk-python-master
- 本地SDK共251文件，根目录及6个子包均为Apache-2.0；Python 3.7+，模块为core/face/nlp/ocr/spark/speech。
- 直接可参考：`xfyunsdkspeech.IatClient/TtsClient/LfasrClient/RtasrClient`、`xfyunsdkocr`通用/印刷/OCR客户端、core HMAC签名与HTTP客户端；不需要face、音色克隆或星火会话Agent进入比赛主线。
- SDK示例通过环境变量`APP_ID/API_KEY/API_SECRET`取凭据，仓库含5个`.env`，后续只读取变量名并做非空密钥审计，不能复制或打印本地值。
- TTS/IAT是Provider客户端参考，不是数字人或Live2D实现；轻量2D导师仍由浏览器状态图+音频幅值驱动。SDK输出继续保持交互层，未经规则/教师门禁不进LearningEvent。

### D:\Code\biyesheji_jiaofu\结果测评
- 用户写的`D:\Code\biyesheji\_jiaofu\结果测评`不存在；真实路径是`D:\Code\biyesheji_jiaofu\结果测评`。
- 目录约11GB且114,991文件，大量来自开源项目依赖/缓存，不能整体复制。`data`约1.34GB，含司法考试、信息抽取、事件检测、类案检索、可解释类案匹配、文书校对、涉法舆情摘要等真实任务数据。
- `OpenSource_Project`约9.67GB，明确包含LawBench/LexEval/MSLR-Bench等；MSLR-Bench有25.5MB多步法律推理数据及FRC/IRAC/LLM评分脚本，适合参考LegalEduEval的IRAC/事实规则一致性指标。
- LawBench/LexEval的大量旧模型输出适合参考任务分类和基线格式，不应直接作为本项目100题Gold或刑法标准答案；需抽题、绑定现行Evidence、去训练污染并由教师审核。
- `.env.example`只用于识别接口变量；真实`.env`不读取、不复制、不提交。

## 2024刑法版本口径纠正
- 中国人大网已确认《中华人民共和国刑法修正案（十二）》于2023-12-29通过，自2024-03-01施行；因此项目正式刑法库的`version_as_of=2024-03-01`口径成立。
- 先前把本地“2024年最新版”直接描述为不可信不够准确。年份不是隔离理由；应分别审查：正文是否与官方2020合并文本+修正案十二七处修改一致、来源链是否为国家法律法规数据库、是否夹带第三方出版者内容、是否可作为正式可引用Evidence。
- 当前正式505条实际上已经合并修正案十二并标记七个修改条文；下一步对本地2024 DOCX做逐条差异审计。即使正文完全一致，第三方页眉/版权污染也只影响其作为主法源的准入，不应否认2024现行版本本身。
- 内容级审计完成：本地“2024年最新版”解析出504条，官方确定性合并版本为505条；缺少第一百九十九条（官方快照保留“删去”占位）。去除罪名标题和水印后493/505条逐字一致，12条仍有差异。
- 修正案十二涉及的第一百六十五、第一百六十六、第一百六十九、第三百八十七、第三百九十、第三百九十一、第三百九十三条七处均与官方合并结果一致，证明该文件确实吸收了修正案十二。
- 不能直接升为正式Evidence的实质理由仍成立：12处“中国刑事辩护网提供”；第一百九十条为旧文本；第三百三十四条之一缺“违”字；三处“甲基苯丙胺”被写成“甲基苯丙*”；另有标点、用词差异。正确定位应为`2024_consolidation_reference_with_content_defects`，不是“年份不可信”。
- 正式刑法仍采用国家法律法规数据库2020正文+官方修正案十二七处确定性合并，共505条；这本身就是截至2024-03-01的现行版本，而非仅使用2020旧法。

## ORCDF对外展示约束
- V0/V1/V2继续用于内部同协议对比、选型和边界审计。
- 比赛PPT/视频不平铺三套版本，只选择一项最能说明“行为数据预训练/知识追踪shadow/受控效果”的结果；同时明确数据来自MOOCCubeX民法/宪法、mastery未校准、不进入刑法正式画像。

## 挑战杯技术导向V2.0可选启发
- V2.0与当前goal高度一致：研究对象应是“法律学科模型技术体系”，产品只承担典型应用验证；无需重启产品化重构。
- 对阶段2最有用的是把结构化推理显式拆为`FactSheet + IssueList + EvidencePack + LegalReasoning + AuditResult`，并让每个事实携带`source_path`。这比只用自然语言Fact数组更适合确定性可见事实门禁。
- 对阶段3最有用的是冻结实验记录字段：`run_id/code_version/dataset_version/model_version/prompt_version/environment/metrics/failure_cases/decision`，可直接纳入LegalEduEval run manifest。
- 对个性化最有用的是三层定位：可解释冷启动作为提交主线，EduBrain/ORCDF作为增强和内部消融，数据驱动深度KT作为后续研究。这与用户要求“ORCDF三版不全部上PPT”一致。
- 可借鉴的比赛叙事是四类数据资产：专业知识语料、推理训练数据、教学交互数据、独立评测数据。当前已完成第一类正式法源治理，推理Schema/fixture将提供第二类可运行样例，LegalEduEval负责第四类，第三类必须等待真实课堂试点。
- 暂不照搬的建议：React重写、LangGraph重构、向量数据库、Docker Compose、150—300知识卡和30—50人正式试用。这些要么与当前Vue/FSM稳定基线冲突，要么超出当前真实证据/时间边界。
- 不把文档中的“多教师可信蒸馏”写成已完成：模型训练归队友，只有交付数据manifest、训练日志和独立评测后才能转为成果。

## EduBrain历史记录吸收（2026-08-31）
- 已完整读取EduBrain根`task_plan.md`、`findings.md`和`progress.md`，将其视为历史实验记录和失败复盘，不把旧任务项直接当作当前仓库指令。
- LegalEduEval必须继承五层隔离经验：结构有效不等于教学有效；同模型初标/二审/盲答可能共同犯错；逐字法条RAG也不能替代规范解释；旧题标准答案可与现行法或独立数据源冲突；任何模型裁决不得自动设置教师发布状态。
- 数据划分必须按原始材料或题族防泄漏，而不只是随机按题切分。MOOCCubeX存在27组完全重复题、全选题、旧法题、截断题和泛化题干；LawBench/LexEval/MSLR的历史模型输出不能进入Gold。
- 评测Runner必须保留失败样本、验证问题、输入/Prompt/数据/法源哈希和`pending`人审状态。复用模型输出时要验证输入哈希和Schema哈希，避免旧结果漂移。
- ORCDF对外只选受控同47题中最有价值的结论，不展示三套主范围AUC横比：主范围数据规模不同，不能归因Q矩阵优劣。可展示候选为“V1相对V0同47题AUC +0.02994，学生成组bootstrap 95% CI不跨0”，并同时标明民法/宪法shadow、LLM-Q provisional、mastery未校准。
- 学生个性化正式主线仍是Evidence-KT冷启动：第一题后不得直接宣称掌握；至少3个合格事件覆盖2题才进入provisional；困惑不直接作负掌握；AI代答只反馈不入长期画像；路径只输出可解释候选，不声称因果最优。
- 公开法学MOOC数据的硬边界保持：126,073条/702人/1,256题来自民法/宪法为主；约26道刑法种子题无关联行为。MOOCRadar法学课仅4名学生/271行为，不能支持刑法参数估计。
- 工程复盘继续应用：全量测试要从`backend`工作目录运行；PowerShell先收集`$rows`再格式化；`${LASTEXITCODE}`要加花括号；同一uv环境不要并行sync；SQLite连接需显式close；浏览器验收等待业务DOM/响应而不是固定sleep。
- 题库规模经验：30道教师试用级题（10知识点×3）足以支持冷启动探测和软件闭环，但不够训练10B模型或证明课堂效果。阶段3的100题是独立评测资产，不与训练样本混用。

## Demo可见性缺口（2026-08-31继续）
- 当前数据治理、LegalReasoning Gate、LegalEduEval与Agent消融的权威结果已进入PPT/JSON，但前端只有RAG/认知/教师等应用页，没有统一技术证据入口。
- Goal要求视频中清晰出现学科数据治理、结构化推理、Agent、LegalEduEval等；仅靠PPT截图不如真实Demo读取审计文件有说服力。
- 下一纵向切片应是只读“技术证据”页：API只投影计数、状态、哈希和证据边界，不返回完整模型答案、内部A/B映射、绝对路径、教师私有字段或密钥配置。
- 页面继续使用现有深色司法档案语言，以数据账簿、推理流水线、评测矩阵和消融成本为主，不新增通用SaaS卡片风格。

## 技术证据Demo完成结论（2026-08-31）
- 新增的`GET /api/competition/technical-evidence`每次读取6份权威JSON/manifest并重新计算SHA-256，只返回计数、状态、成本、边界和安全模型路由；完整C0/C1文本、内部A/B映射、教师私有字段、答案、学生原文、密钥、鉴权头和绝对路径均不返回。
- 前端“技术证据”以总账、数据治理、推理/评测、Agent/边界四页展示真实投影，不在Vue中硬编码实验结果；pending与not_gold作为主信息显示。
- 1500×980与780×900两轮均验证5个技术链节点、4个总账卡、4个数据行、11项Gate、6个负例、5类评测、4条模型路由、2种Agent条件和4项pending；横向溢出、私有字段、console/page/HTTP/request错误均为0。
- 持久化报告首轮仍含本机绝对artifact目录，公开复制前已改为仓库相对路径并重跑；这说明页面脱敏和验收产物脱敏必须分别检查。
- `competition_submission/03-Demo/technical-evidence/`已固化4张桌面图、1张窄屏图、2份报告和SHA说明，可作为视频10—84秒及PPT第4/6/7/8页的可复核素材。
- 机器侧入口完成不解除外部边界：100题教师Gold、Agent双教师盲评、Qwen3-8B队友交付、2名真实用户、伦理签字和V2视频团队终审仍pending。

## V2视频DRAFT前半段审片（2026-08-31）
- 新成片为137.6秒、1920×1080、H264/AAC、11段字幕，技术证据新增段位于4.1—20.1秒；音频无超过1.2秒静音，最大配音加速系数1.19429。
- 0.8、4.6、11.5、19.0、21.0、39.0、54.5秒抽帧均无登录残帧、账号、token或私有字段；技术总账→推理评测→Agent切换正确，not_gold/pending可见。
- 字幕保持两行以内，未遮挡核心指标、权威Evidence或教师门禁状态；黑底会遮挡少量底部辅助说明，当前可接受，后半段仍需继续检查。

## V2视频DRAFT后半段审片与修正决策（2026-08-31）
- 66、85、100、132、137.2秒的教师、INV、PR和片尾边界清楚，AI配音DRAFT标识全程可见；INV明确披露源文件阶段标记不一致，PR明确“不起诉分支不等于专家结论”。
- 77秒Agent静态页字幕压住部分`2→3/耗时/token` KPI；决定全片字幕从FontSize15/MarginV42收敛到13/24，使字幕更靠下且占用更小。
- 117秒案件段顶部仍显示合成账号`student@example.com`；虽非真实PII，仍按“登录凭据不进正式片段”的严格口径，在合成时对header账号/退出区域做确定性纯色遮罩，并在审计声明不修改法律或学习证据。
- 新技术证据配音1.19429倍略快；将该段从16.0延长到19.2秒，使用最后Agent边界帧静止补足阅读时间，预计总片长140.8秒。
- 140.8秒v2验证显示字幕/KPI已改善且合成邮箱已被遮住，但技术段末尾形成1.297秒静音，蓝色遮罩视觉突兀。最终调整为18.6秒（约1.02倍配音）及两个深色小遮罩，预计140.2秒。

## 讯飞ASR/TTS真实接通结论（2026-08-31）
- 外部配置实际使用`APPID/APIKey/APISecret`；`start.py`仅在子进程环境映射为`XFYUN_*`，显式环境优先，不复制或打印值。
- 项目直接实现讯飞在线TTS v2与流式IAT v2 WebSocket/HMAC，不vendor参考SDK；错误消息禁止传播可能含签名URL的异常正文。
- 真实直接调用：TTS 1次生成207,892字节、16kHz/单声道/16bit/6.495秒WAV，IAT 1次转写“罪刑法定原则要求法无明文规定不为罪法无明文规定不处罚。”，归一化相似度1.0、法学词4/4、会话标识均返回。
- 产品API再次真实完成TTS succeeded→私有下载→IAT needs_review；当前进程ASR/TTS切为available，数字人仍not_connected，媒体job2、资产1、LearningEvent0（独立API smoke库）。
- 1500×980浏览器完成TTS播放、同音频IAT、上传音频IAT、数字人边界；3项available能力，私有/console/page/HTTP/request错误0。blob关闭中止被确认仅为本地URL生命周期，不计http(s)失败。
- PPT第11页首轮截图过小且标题遮挡；第二轮放大后出现叠字；第三轮横向能力卡证据带无覆盖，显著说明“单条相似度1.0不是ASR准确率”、ASR needs_review和Avatar NOT CONNECTED。独立复审无阻断项。

## 实时多模态定义纠正（2026-08-31）
- 用户明确“多模态”指用户与平台实时语音交流，不是先上传音频文件再处理。
- 当前TTS文件生成、IAT文件转写、产品API与视频只证明Provider接通和音频资产安全，不能证明实时语音对话完成。
- 比赛主链必须改为浏览器麦克风实时PCM分片→后端WebSocket→讯飞流式IAT partial/final→法学回复→讯飞TTS音频回传/播放→继续下一轮；文件上传保留为兼容/审计工具。
- 只有真实流式E2E与UI通过后才能重新标记多模态完成；数字人仍后置。

## 实时语音代码基线审计（2026-08-31）
- 当前未提交代码只新增了`IflytekStreamingIATSession`骨架；`ws_server.py`尚无独立实时语音端点，前端仍以文件上传和TTS→IAT回送为主，因此当前不满足实时语音对话定义。
- 现有主WebSocket已经通过`Sec-WebSocket-Protocol: simlaw-auth,<JWT>`鉴权并默认禁止query token；实时语音端点应复用该方法，不能把JWT写入URL。
- 讯飞既有IAT协议按16kHz、单声道、16bit raw PCM、每40ms约1280字节工作；浏览器应持续分片发送，而不是先录制成文件。单turn将限制为60秒、严格单活动turn和有序seq。
- final转写应通过`KnowledgeService.search(top_k=3)`进入受治理Evidence回复；模型仅生成形成性口语解释，引用必须限制在当前EvidencePack，失败时确定性降级，不能创建LearningEvent或正式评分。
- TTS可以在final后整段生成WAV并回传自动播放；“实时”核心是用户麦克风到partial/final的持续流式交互，不要求当前阶段把TTS也改成流式音频块。
- 讯飞动态修正结果可能携带`pgs=rpl`和`rg`范围；流式聚合器需支持替换旧片段，否则partial累积可能重复或错误。

## 讯飞官方WebAPI复核（2026-08-31）
- 官方IAT文档明确该接口用于1分钟内即时语音，支持一边上传一边返回文本；16k/8k、16bit、单声道PCM，最长60秒，建议PCM每40ms发送1280B，首/中/末状态为0/1/2，结束帧必须发送。
- 当前文档的后端静音检测参数为`eos`；实时展示应设置`dwa=wpgs`，并按`pgs=apd`追加、`pgs=rpl`结合`rg=[start,end]`替换旧返回片段。现有骨架的`vad_eos`和纯累加逻辑需要修正。
- 官方TTS文档确认`wss://tts-api.xfyun.cn/v2/tts`、HMAC-SHA256鉴权、文本一次传输且`data.status=2`、UTF-8与base64文本、raw PCM可分片返回；base64前文本必须小于8000字节。
- 当前比赛链允许在final转写后等待整段TTS再自动播放；IAT是真正持续流式，TTS仍由官方WebSocket接收多音频片段后合并WAV。后续若实测首包延迟影响交互，再把TTS片段直接推送浏览器，不先制造未验证复杂度。
- 官方文档只作为协议事实来源，不自动证明本项目实时链路已完成；仍须浏览器两轮E2E与真实网络证据。

## 实时语音首轮真实浏览器结果（2026-08-31）
- 使用Chromium实时媒体设备通道按真实时间播放16kHz法学WAV作为麦克风输入，浏览器AudioWorklet持续采集并发送PCM；后端没有收到文件上传，而是收到实时`voice_audio`分片。
- 两轮均完成`session_ready→partial→final→reply_generating→reply_text→TTS reply`；累计54个partial、2个final、2个Evidence约束模型回复、2个讯飞TTS，LearningEvent timeline为0→0。
- 页面、console、page error、HTTP、request failure和私有字段泄漏均为0；两条final都保留“罪刑法定”核心词，但循环fixture在新一轮开始点可能从句中间采集，不能把它当独立ASR准确率测试。
- 首轮暴露真实体验缺口：模型回答生成的TTS分别67.048秒和60.368秒，且第二轮可在上一段仍播放时启动。需要把口语回复缩到50—90汉字，并在播放中禁用下一轮；首轮只证明链路跑通，不作为最终体验证据。

## 阶段12用户反馈与ASR根因（2026-09-01）
- 用户要求RAG正文出现行末引用：悬停可看截断的法律/案件摘要，点击可查看完整来源，且要融入现有司法档案视觉。
- 当前可信RAG已有`TypicalQuestionSource`完整法源/案例结构；分层解惑已有逐字citation与audit Evidence；实时语音已返回evidence_id、标题、条号、quote、时效。可建立一个统一证据标记/抽屉组件，不需要再发明后端来源。
- 已用同一`build_backend_env`反馈环复现ASR未连接：仓库没有`.env`，直接`python start.py`时`XFYUN_APP_ID/API_KEY/API_SECRET`全部False；只有显式`--model-config E:\guabangjieshuai\EduBrain\.env.example`才全部True。这是启动配置没有持久化，不是讯飞随机故障。
- 页面另有状态误导：凭据存在但本进程尚未成功调用时仍显示`not_connected`；IAT握手成功后也要等TTS整轮结束才标available。应拆成`not_configured/configured_not_verified/available`，并在IAT握手成功即晋级ASR。
- 当前波形是CSS循环，与真实麦克风能量无关；即使设备静音也会动。需要从AudioWorklet采样计算RMS，显示真实输入电平、设备名和无输入提示。
- 当前默认TTS为老`xiaoyan`。官方发音人资料提供`x4_lingxiaoxuan_assist`等中文交互女声；必须先用当前应用真实授权测试，再设为首选，未授权时回退`xiaoyan`。

## 阶段12最终实现与集成证据（2026-09-01）
- 用户授权将`E:\guabangjieshuai\EduBrain\.env.example`中的白名单运行配置迁移到仓库本地`.env`；`.env`已被Git忽略。当前本地变量名覆盖OpenCode主模型、DeepSeek官方回退、讯飞APPID/APIKey/APISecret和TTS音色，不记录或输出任何值。
- `start.py --sync-env-from <path>`只同步显式白名单；普通`python start.py`可直接读取仓库`.env`。前后端能力状态使用`not_configured/configured_not_verified/available`，IAT WebSocket握手后即晋级ASR，TTS真实合成成功后晋级TTS。
- 真实授权测试中`x4_yezi`调用成功，生成180,942字节、16kHz WAV，SHA-256为`be4950d12f267f492df5731110a51f5367393b4312935467c906eaff5d5876cb`；当前首选为`x4_yezi`，失败回退`xiaoyan`。这只证明真实Provider调用通过，不构成自然度主观评分。
- 统一`EvidenceCitations`已经接入可信RAG、分层解惑和实时语音回复：正文行末编号、悬停截断摘要、点击完整抽屉、原始来源链接、快照/SHA/版本/风险字段，并固定“检索相关不等于法律蕴含”的边界。
- 最终浏览器集成门禁使用Chromium真实媒体设备通道按实时钟播放确定性WAV，得到6个RAG引用标记、200个PCM分片、30个partial、1个final、1个Evidence回复、`x4_yezi` TTS、LearningEvent 0→0、文件上传0以及console/page/HTTP/request错误全0。
- 此浏览器证据证明实时PCM→讯飞IAT→Evidence回复→讯飞TTS链路和页面诊断可用，不证明真实课堂多说话人ASR准确率；真实用户手持麦克风测试与课堂试点仍需团队执行。
