# 任务计划：刑法学科技术主线收敛

## 目标
在不替代模型队友训练Qwen3-8B、不伪造专家/用户/学习效果的前提下，完成可展示的法学数据治理、Evidence约束推理、LegalEduEval-v1、Agent C0/C1消融和轻量2D数字导师，并同步PPT、视频、效果报告和公开提交包。

## 当前阶段
阶段11：实时语音多模态对话（进行中）

## 阶段

### 阶段1：四层刑法数据治理
- [x] 盘点`E:\guabangjieshuai\EduBrain\laws`真实文件规模、类型和目录
- [x] 实现SHA、重复组、来源/层级/刑法相关性/隐私/准入候选流水线
- [x] 生成`corpus_inventory.json`、发布manifest、拒绝日志、知识-Evidence链接、DATASET_CARD
- [x] 将813正式法源与4173候选材料严格分层
- [x] 内容级复核本地“2024年最新版”刑法与官方2020正文+修正案（十二）的差异，纠正“年份即不可信”的旧表述并补充版本链审计
- **状态：** completed

### 阶段2：Evidence约束法律推理
- [x] 冻结Issue-Fact-Rule-Application-Counterargument-Conclusion-Uncertainty Schema
- [x] 增加法源/条号/quote/Evidence范围/可见事实/要件/反方/弃权/注入门禁
- [x] 形成正负fixture、JSON和Markdown审计
- **状态：** completed

### 阶段3：LegalEduEval-v1
- [x] 建立100题候选集与split/hash/review状态
- [x] 覆盖25/25/20/15/15五类任务和重点负例
- [x] 审计`D:\Code\biyesheji_jiaofu\结果测评`及用户补充路径中的法学评测数据、指标和Runner，选择性复用
- [x] 实现模型无关Runner与E0/E1/E2/E3 pending对照Schema
- [x] 输出自动指标、人工Rubric、延迟/token/费用字段
- **状态：** completed（教师逐题Gold审核与E0—E3真实运行作为外部/模型交付后续）

### 阶段4：Agent C0/C1消融
- [x] 固定CaseBundle、学生输入、模型/Prompt/Evidence条件
- [x] 运行静态C0与聚焦状态机C1
- [x] 比较流程、争点/要件、引用、反方、成本、故障；生成匿名双教师盲评包并保持pending
- **状态：** completed（双教师盲评待真实人员填写）

### 阶段5：轻量2D数字导师
- [x] 生成原创4状态透明WebP
- [x] 审计`E:\guabangjieshuai\EduBrain\websdk-python-master`中的讯飞ASR/TTS/OCR/数字人示例、鉴权、许可证与可复用Provider边界
- [x] 实现呼吸、微摆、眨眼和TTS/浏览器朗读嘴形切换
- [x] 只在解惑、Evidence警告、路径推荐显示，固定AI形成性标识
- [x] 保留正式Live2D/讯飞数字人替换接口
- **状态：** completed

### 阶段6：技术叙事和比赛材料
- [x] PPT调整为数据→Evidence→推理→评测→应用
- [x] 170秒V2视频脚本加入数据治理/推理/LegalEduEval/Agent可视证据（真实成片待团队重录）
- [x] 更新机器效果报告、LegalEduEval Dataset Card、技术报告和机器交付清单
- [x] 保持微调、专家、用户、签署真实pending；不代填、不代签
- [x] ORCDF三版本仅作内部选型审计；外部PPT只保留一条受控结论
- [x] 最终公开包不在外部pending项完成前重建，避免把DRAFT误发为最终版
- **状态：** completed_machine_scope

### 阶段7：Demo技术证据统一展示
- [x] 建立只读、脱敏的技术证据API，聚合数据治理、推理Gate、LegalEduEval、Agent消融与2D导师审计
- [x] 新增与现有司法档案视觉一致的“技术证据”前端入口
- [x] 在1500×980与基础窄屏验证数据/推理/评测/Agent/边界均可见且0私有/网络错误
- [x] 同步170秒视频脚本与技术材料中的真实Demo路径
- **状态：** completed_machine_scope（最终视频仍待团队按V2脚本重录与终审）

### 阶段8：V2技术主线视频增量素材
- [ ] 录制不含登录凭据的“技术证据→数据治理→推理/评测→Agent/边界”真实点击段
- [ ] 将新段增量接入现有121.6秒AI配音DRAFT，保持总长低于180秒
- [ ] 核对AI标识、字幕、音频、关键帧、浏览器错误、隐私与证据边界
- [ ] 同步公开视频审计、V2脚本/PPT状态，保留团队完整审片与批准pending
- **状态：** completed_machine_scope（140.2秒AI配音DRAFT已审计；团队完整审片仍pending）

### 阶段9：讯飞ASR/TTS真实接通
- [x] 实现讯飞IAT/TTS v2 WebSocket、HMAC签名、私有音频下载和needs_review边界
- [x] 使用仓库外`.env.example`真实生成WAV并真实转写，公开音频/JSON/Markdown审计
- [x] 通过产品API和1500×980浏览器验证ASR/TTS available、数字人not_connected
- [x] 更新技术主线PPT第11页并完成网页/PowerPoint双重渲染
- [x] 保持ASR LearningEvent=0、正式评分=false、数字人后置
- **状态：** completed_machine_scope（真实课堂ASR审核流程和数字人授权后续）

### 阶段10：讯飞多模态视频增量
- [x] 录制不含登录凭据的真实TTS→私有WAV→IAT→数字人边界点击段
- [x] 将新段加入140.2秒AI配音DRAFT并保持≤180秒
- [x] 更新视频审计、18帧总览/审片包和V2脚本状态
- [x] 复核AI标识、字幕、音频、隐私、网络与数字人后置边界
- **状态：** completed_machine_scope（163.2秒DRAFT；团队完整审片仍pending）

### 阶段11：实时语音多模态对话
- [x] 浏览器麦克风实时采集并发送16kHz/16bit/单声道PCM分片，不以文件上传作为主交互
- [x] 后端独立鉴权WebSocket持续转发讯飞IAT，向前端推送partial/final转写，并限制单turn 60秒/有序分片/单活动turn
- [x] final文本进入法学回复服务，讯飞TTS生成音频回传并自动播放
- [x] 支持同一页面多轮push-to-talk，显示AI标识、needs_review和LearningEvent 0
- [x] 使用真实讯飞流式网络完成至少两轮浏览器E2E（实时媒体设备按真实时钟播放PCM fixture），确认partial/final、TTS自动播放、桌面/窄屏及0控制台/HTTP/隐私错误
- **状态：** completed_machine_scope（已完成浏览器实时协议和真实讯飞两轮；多说话人真实课堂ASR准确率仍需试点，数字人继续后置）

### 阶段12：行末证据引用与实时语音可用性修复
- [x] 建立统一正文行末引用标记：悬停显示截断法源/案例摘要，点击打开完整证据抽屉
- [x] 接入可信RAG、AI分层解惑和实时语音Evidence，保留法源版本、时效、哈希与语义边界
- [x] 修复普通本地启动不加载外部讯飞配置的问题，区分未配置/待验证/已连接
- [x] 麦克风显示真实输入电平、设备名、安全上下文与权限错误，不用纯CSS波形假装有输入
- [x] 更换并真实验证自然女声，未授权时可靠回退且不暴露Provider错误正文
- [x] 桌面/窄屏/无配置/真实配置回归通过后同步材料、提交并推送
- **状态：** completed_machine_scope（真实课堂ASR、多说话人准确率、教师/用户审核和数字人仍按总体边界待后续）

## 关键边界
- 模型蒸馏、LoRA/SFT、训练日志和模型产物由队友负责；我方只做接口和统一评测。
- 4173个文件是候选语料，不是高质量训练集；813条才是当前正式规范法源。
- Silver不称Gold；自动门禁不称专家准确率；软件评测不称学习效果。
- ORCDF继续保持民法/宪法shadow、mastery未校准边界。
- 不因文件名含“2024最新版”自动隔离；以官方来源、逐条内容、修正案版本链、污染/版权字段分别判定内容正确性和Evidence准入。
- 不使用Docker作为开发主线，不破坏用户未跟踪文件。

## 错误日志
| 错误 | 次数 | 处理 |
|---|---:|---|
| 数据治理审计把`model_calls: 0`计数放入布尔`all()`导致门禁误失败 | 1 | 改为`model_calls_zero: true`，实际次数移入`execution_counts` |
| 首次组合PowerShell多行命令时JavaScript模板字符串解析失败 | 1 | 改为显式字符串数组按换行拼接，避免续行符进入JS语法 |
| LegalReasoning fixture使用`case_bundle_id`而构造器接收`case_id` | 1 | 在Runner边界显式映射字段，保留fixture领域命名 |
| 从仓库根目录运行`unittest discover`导致8个既有测试模块找不到`src/scripts` | 1 | 按仓库导入约定切到`backend`目录运行全量测试，不修改业务代码 |
| Git提交命令使用未注入的环境变量，首次提交标题误为`-m` | 1 | 立即仅amend提交消息为英文Conventional标题+中文说明/验证，提交内容未变 |
| 结果测评库存命令再次在`foreach`结果后直接接管道触发empty-pipe ParserError | 1 | 按EduBrain复盘改为`$rows=@(...)`收集后统一输出，不重复原写法 |
| LegalEduEval Runner对JSON字符串评分时换行转义导致关键词覆盖少算 | 1 | 改为递归提取输出真实字符串后评分，不放宽门禁 |
| Python manifest字典误写JSON布尔值`true`导致生成器NameError | 1 | 改为`True`；错误发生在写产物前，旧100题未破坏 |
| Agent消融首轮fact catalog生成`FACT_1`，违反Schema至少两字符后缀 | 1 | 改为`FACT_F01`格式并新增正则测试；首轮保留为夹具失败，不作正式对比 |
| 复制ImageGen产物时再次使用未注入的`$env:SRC`导致源路径为空 | 1 | 改用明确LiteralPath；没有生成错误文件，只创建目标目录 |
| 动态构造路径清理本轮PNG中间件被安全策略拒绝 | 1 | 不重复动态删除；改用9个已知仓库内LiteralPath做非递归精确清理 |
| 轻量导师专项测试从仓库根运行导致`src`不可导入 | 1 | 新测试显式加入backend路径；既有测试按约定从backend目录运行 |
| 补丁工具不支持删除PNG二进制中间件 | 1 | 对9个本轮生成文件逐一暂存后`git rm`，受控删除成功；只保留4张WebP和manifest |
| Guizang V2首轮静态校验发现第9页两张图未绑定S16槽位 | 1 | 给article、frame和img补`s16-brief-16x10`后重跑 |
| Guizang V2 PPTX导出使用项目`.venv`缺`python-pptx` | 1 | 改用Codex工作区自带文档Python，不污染项目依赖 |
| 技术证据窄屏smoke只等待静态标题，未等待异步数据即统计为0 | 1 | 等待首个pipeline节点后再断言；业务页面/网络未报错 |
| 首轮持久化`report.json`写入本机绝对artifact目录 | 1 | 公开复制前改为仓库相对路径，并约束artifact必须位于仓库内；桌面/窄屏重跑通过 |
| staged密钥定位命令再次把`foreach`结果直接接管道导致ParserError | 1 | 按EduBrain历史复盘先收集`$rows=@(...)`再格式化；随后确认唯一`sk-`命中是Schema字符串子串并用左边界规则消除误报 |
| 第一次远端核验把`git ls-remote ... -split`写在同一赋值表达式，PowerShell按字符解析成`REMOTE=7` | 1 | 改为先保存`$remoteLine`再拆分；首次重试遇GitHub瞬态SSL失败，第二次成功确认本地/远端`762c75b`一致 |
| 140.8秒视频v2出现1.297秒静音且合成账号遮罩为不自然蓝块 | 1 | 技术段由19.2调为18.6秒以维持约1.02倍语速；遮罩拆成两个贴合header背景的深色小矩形，另建v3重验 |
| 审片包首次用项目`.venv`构建缺`pypdf`，系统Python又缺`reportlab` | 1 | 按PDF技能加载Codex bundled文档Python，依赖齐全且不污染项目锁文件；构建成功并用Poppler渲染4页 |
| 统计审片包SHA时再次把`foreach`结果直接接管道触发ParserError | 1 | 立即改为`$rows=@(...)`后格式化，未写文件；保留为禁止复发案例 |
| `.env.example`变量库存用第二次`-match`覆盖`$matches`，错误显示3个`api_key` | 1 | 改用独立`[regex].Match()`对象；确认真实讯飞变量为`APPID/APIKey/APISecret`，值只统计配置状态不输出 |
| 从backend目录首次跑编译/测试仍使用根目录相对路径 | 1 | 改为`..\.venv`与`..\requirements.lock.txt`；离线12/12通过 |
| 第一次产品TTS API未先创建sandbox而404 | 1 | 按前端真实流程先`/api/sandbox/ensure`，未绕过隔离；第二次TTS/IAT成功 |
| SQLite读取一行Python因PowerShell引号破坏导致SyntaxError | 1 | 使用here-string管道给Python stdin，只读查询成功 |
| 浏览器关闭本地`blob:`音频产生`ERR_ABORTED`假request failure | 1 | smoke只排除`blob:`协议，继续严格统计所有http(s)失败；全新栈重跑0错误 |
| 全量119测试唯一失败仍期待旧SDK catalog字符串 | 1 | 更新测试为项目真实`online_tts_v2/streaming_iat_v2`适配器，未放宽密钥与not_connected门禁 |
| PPTX回渲染首次比较旧第11页缓存，差异82.08 | 1 | 确认PPTX内图像SHA已是最新；用PowerPoint COM无窗口重新导出12页，差异恢复0.094643 |
| 精确删除未使用全屏PPT图片被安全策略拒绝 | 1 | 不改用更激进删除命令；文件保持未跟踪且不纳入精准staging，不影响提交 |
| 将“文件式TTS→IAT往返”按多模态主功能收口，与用户实时语音交流要求不一致 | 1 | 用户明确标准后撤回完成判断；文件上传降级为兼容/审计工具，新增实时麦克风PCM→IAT partial/final→法学回复→TTS播放主链 |
| 实时语音专项首轮14/15通过，测试把安全布尔字段`api_key_configured`误判为密钥泄露 | 1 | 不放宽响应安全；新增模型路由白名单投影并把测试改为检查secret与api_base不出现 |
| 从仓库根启动本地栈时误用backend目录的`..\.venv`相对路径 | 1 | 进程未启动、无外部调用；改用仓库根`.\.venv`，不重复错误命令 |
| 短答修复后的真实smoke第一轮完成，但“AI语音播放中”同时命中状态标题和禁用按钮导致strict selector失败 | 1 | 产品链路无错误；将断言收紧到`.voice-runtime strong`并从新账号完整重跑两轮 |
| 完整回归124/125，旧轻量导师测试仍期待`implemented_real_call_required` | 1 | 实时浏览器已真实通过，更新旧断言为`implemented_realtime_websocket`并额外校验live PCM client，不回退真实能力状态 |
| 最终协议审计两轮成功但Google Fonts外部请求瞬态`ERR_CONNECTION_CLOSED`使smoke非零 | 1 | 语音/API均无错误且386个PCM帧、0文件上传已证明；移除非必要远程字体，改用系统中文宋体/Cascadia/Consolas离线栈后重验 |
| PPTX内容QA尝试使用bundled Python的markitdown但模块不存在 | 1 | 当前PPTX为逐页验收截图，文本提取不是内容权威源；改用slides.html内容源、Guizang静态门禁、浏览器截图和PowerPoint回渲染四层QA，不污染项目环境安装包 |
| 实时语音视频录制器启动前误用不存在的`fs.isFileSync` | 1 | 浏览器/云端均未启动；改为`existsSync + statSync().isFile()`后重跑，验收门槛不变 |
| 效果报告PDF文本门禁未匹配换行后的`OCR/数字人未连接` | 1 | 报告实质文本已生成；把该项移到去空白compact门禁，不删除或弱化状态要求 |
| 并行重建视频审片包与效果报告时，效果报告读取被安全清理中的视频MANIFEST而FileNotFound | 1 | 视频包已成功恢复；依赖链改为先视频包、后效果报告串行执行，不重复视频重建 |
| PowerShell中误用Bash here-doc运行空Python片段导致ParserError | 1 | 无文件/进程变化；改用`python -c`或PowerShell here-string，不重复`<<`语法 |
| 阶段12后端专项从backend目录误用根目录`.\.venv`路径 | 1 | 测试未启动；改用`..\.venv`与`..\start.py`后重跑 |
| 只读检查`.env`存在性时在PowerShell哈希值表达式内直接使用`if`导致命令错误 | 1 | 变量名白名单仍成功输出且未打印值；后续先用独立变量计算文件大小，不重复内联`if`写法 |
| 在仓库根目录用`..\\.venv\\Scripts\\python.exe`检查本地环境导致路径不存在 | 1 | 改用根目录`.\\.venv\\Scripts\\python.exe`；只输出布尔配置状态，未输出任何密钥值 |
