# 任务计划：法律/教材/题目混合RAG

## 目标
把2,024份官方来源canonical法律/法规/司法文件/案例逐份核实并按真实身份接入多来源EvidencePack；813条保持刑法课程核心规范基线，57,051条保持检索记录口径。沿用既有Embedding，不重复计算向量；完善效力元数据、层级准入、案例父段回填、前端引用和比赛材料。

## 当前阶段
阶段8：多来源EvidencePack与逐份效力核实（进行中）

## 阶段

### 阶段1：只读库存和计划
- [x] 核对SiliconFlow配置状态和模型名，不输出密钥
- [x] 盘点laws四类候选文本
- [x] 盘点题库规模和数据用途
- [x] 找到JEC-QA章节教材
- [x] 形成独立实施计划
- **状态：** completed

### 阶段2：canonical manifest和分块
- [x] 法律/行政法规/司法解释/案例去重和规范化
- [x] 案例使用document→语义父段→检索子块的父子分段，并校验parent_id完整性
- [x] 教材章节/小节分块
- [x] 题目public/private隔离
- [x] 输出chunk JSONL、Schema和hash，不调用API
- **状态：** completed（真实构建16项确定性门禁通过；Embedding/Reranker仍0调用）

### 阶段3：qrels/NLI人工模板
- [x] 120条分层检索qrels候选
- [x] 180对NLI三分类标注模板
- [x] 冻结候选类型、标签状态和人工复核边界
- **状态：** completed（全部为待教师复核候选，Gold标签为0）

### 阶段4：SiliconFlow小样本探针
- [x] 300块分层API调用（Embedding）与30组Reranker探针
- [x] 核验国内官方URL、模型、1024维、批量、用量、延迟与端点回退
- [x] 固化Embedding失败回退BM25F、Reranker失败回退RRF的客户端边界
- **状态：** completed（真实API成功；候选相关性仍待教师复核）

### 阶段5：三库向量索引
- [x] legal_authority：54,463块
- [x] textbook_explanation：1,404块
- [x] question_public：1,184题；question_private明确禁用
- [x] 1024维归一化float16 NPY+metadata+manifest+断点续跑+SQLite词法索引
- **状态：** completed（57,051条真实索引，三路行数/向量/词法索引一致）

### 阶段6：Hybrid集成
- [x] BM25F+Dense并行
- [x] RRF融合和精确条号保护
- [x] Reranker对RRF候选重排；失败时降级RRF
- [x] EvidencePack治理回投、公开分库API与feature flag
- [x] Embedding失败降级BM25F，明确不存在法名/条号可靠弃权
- **状态：** completed（真实HTTP验证通过；公开响应内部字段泄漏0）

### 阶段7：评测与材料
- [ ] R0—R4检索消融
- [ ] Evidence/NLI/端到端RAG
- [ ] 题目答案隔离和教材分层
- [ ] PPT/视频/技术报告
- **状态：** pending

### 阶段8：多来源EvidencePack与逐份效力核实
- [ ] 扩展Evidence Schema：法律、行政法规、司法文件、案例、教材、学习资源
- [ ] 逐份生成2,024条验证记录，确定性批处理优先，疑难项并行模型核实
- [ ] 合并官方元数据、模型核实与增量缓存，输出状态统计和待人工冲突清单
- [ ] 更新运行时层级准入、EvidencePack投影、案例父段回填和无答案弃权
- [ ] 更新行末引用悬浮/详情，友好显示身份、效力、父段和使用范围
- [ ] 完成8类真实HTTP/降级验证，重跑R0—R4候选消融
- [ ] 同步README、技术报告、效果报告、PPT和公开DRAFT包
- [ ] 视频V3继续等待用户另行确认，不生成或覆盖
- **状态：** in_progress

## 关键决定
- “覆盖laws全部”指四类canonical唯一文档，不重复索引raw/TXT/ZIP/分类汇总。
- 法律、教材、题目使用独立索引和权威层级。
- 案例Dense/BM25F/Reranker检索短子块，命中后按parent_id回填完整语义父段；不把整案直接作为单向量。
- 题目Embedding用于相似题/变式/错因/章节映射，不用于判分或掌握度。
- 教材进入解释层，不覆盖现行法。
- 运行时固定为BM25F + Embedding召回、RRF融合、Reranker重排；Embedding失败降级BM25F，Reranker失败降级RRF。
- 先有qrels再决定Dense/Hybrid是否优于BM25F。
- 当前版权不作为研发阻塞项；对外提交风险另行处理。
- 用户界面只展示来源名称、条号、版本/时效、正文和必要风险提示；SHA、内部ID、构建审计留在后端与技术报告。
- 构建检查分为必须阻断项与非阻断质量提醒；答案泄漏、Schema损坏、父子断裂和绝对路径泄漏仍硬阻断，元数据完整度等只提示。
- 产品完成优先：SHA、内部Evidence ID、构建审计和机器门禁状态不进入学生/普通展示界面；非关键质量项不阻塞功能演示与交付。
- 2026-09-03用户新口径：教材/题目版权不作为本项目非商用研发与比赛阻塞；2,024份官方来源canonical文档不再因案例隐私或人工复核默认隔离，自动核实后按真实身份进入EvidencePack。
- 813条只表示刑法505+刑诉法308的课程核心规范基线，不是EvidencePack唯一可引用范围；57,051只表示检索记录。
- unresolved不阻塞索引和演示，但回答必须显示效力尚未完全核实；答案泄漏、权限/密钥泄漏、Schema/ID/父子关系损坏、引用错配和不存在法条确定回答仍硬阻断。
- 司法解释来自国家法律法规数据库官方下载，不继续为剩余349份逐条追详情URL；本地官方原件对应即允许进入EvidencePack，保留效力未完全核实提示。

## 错误记录
| 错误 | 次数 | 处理 |
|---|---:|---|
| PowerShell复杂foreach/内嵌if解析失败 | 3 | 改为多行、先计算变量、再收集rows |
| 首次大补丁预期active plan名称不一致 | 1 | 不覆盖现有technical plan，改为独立计划目录和文档 |
| 首次真实构建出现1个重复chunk_id | 1 | `重新组建仲裁机构方案`内部同一第二条重复；保留原文并把section_index纳入稳定ID，不放宽唯一性门禁 |
| 隐藏媒体hash后认知冒烟仍要求3行证明字段 | 1 | 页面正确减少为状态/范围2行；更新测试断言，不把hash恢复到用户界面 |
| 媒体状态人性化后认知冒烟仍等待旧“契约已调用”文案 | 1 | 页面改为“接口已准备/尚未连接”，同步测试等待新用户文案 |
| SiliconFlow最小探针经`.ai`降级到全球`.com`后401 | 1 | 用户补充的是国内官方文档；调整为`.ai`失败后优先国内`.cn`，再保留全球端点，不改Key |
| 尝试删除生成的题目旧索引被命令安全策略拒绝 | 1 | 不再删除；把旧索引在同一生成目录内改名留档，再生成包含题干与选项的新索引 |
| PowerShell单行Python索引审计出现ScriptBlock解析错误 | 1 | 改用单引号here-string传入Python代码，审计成功；不重复复杂内联转义 |
| 真实检索smoke从backend目录运行却把backend误当仓库根目录 | 1 | 使用`Path.cwd().parent`明确仓库根；索引与客户端专项测试已通过，不涉及索引重建 |
| 从仓库根直接加载`test_knowledge_contracts`缺少backend模块路径 | 1 | 按该测试既有运行约定切到backend目录执行，不修改业务代码规避测试上下文问题 |
| 会话中断导致embed_text索引重建进程句柄消失 | 1 | build_state已保留590/1702批，确认无活动构建进程后按相同参数断点续跑，不从头开始 |
| NLI模型初筛12批均遇OpenCode CreditsError 401 | 1 | 这是用户明确授权回退的额度耗尽而非无效Key；仅将CreditsError/Insufficient balance识别为瞬态，普通401仍不回退，改走DeepSeek官方 |
| embed_text索引1702批中2批国内端点连接失败后全球端点401 | 1 | 1700批状态已保存；按断点续跑只重试2个失败批次，不重复已完成数据 |
| Guizang V3首次截图模型接口蓝色中栏末行贴边 | 1 | 将说明拆为两行并重新渲染，保持S05原骨架和投屏字号 |
| 项目.venv导出PPTX缺少python-pptx | 1 | 不污染项目依赖；使用Codex工作区已配置的文档Python继续导出 |
| 工作区Python没有markitdown可做PPTX文本提取 | 1 | PPTX为逐页验收图，改用python-pptx核对13页/16:9/每页1张全页图，并用HTML源做占位词与禁用词检查 |
| 从仓库根误运行Guizang相对路径build/validator | 1 | 未改文件；切回deck目录按原脚本约定运行，不再重复错误cwd |
| 项目.venv重建效果报告缺少pypdf | 1 | 不修改项目依赖；改用Codex工作区文档Python执行报告构建 |
| 公开包缺旧视频审片25帧接触表而停止 | 1 | 视频V3尚待确认且接触表非核心赛题交付；改为存在则纳入，核心PPT/视频/报告/伦理/源码仍保持缺失阻断 |
| 首次PPT批注提交命令的中文引号被Git误解析为pathspec | 1 | 暂存内容未丢失；改用PowerShell单引号消息重试并成功提交 |
| 公开包覆盖旧ZIP时Windows返回Invalid argument | 1 | 效果报告已成功；把旧DRAFT ZIP非破坏性移到tmp留存，解除目标占用后再生成 |
| 文号通用正则把日期末尾“日”并入国务院令 | 1 | 收紧令号发布机关模式为主席令/国务院令/中央军委命令/部委令，避免跨日期贪婪匹配 |
| 首轮2,024份核实有1份宪法未匹配raw | 1 | 宪法原件位于raw_data根而非“法律”子目录；补充根目录扫描，缓存仅重算原件未匹配项 |
| 多来源Evidence测试中教材无article_ref触发旧Schema最短2字限制 | 1 | article_ref对条文可填写、对教材/案例/题目允许为空；引用身份仍由source_type与allowed_usage约束 |
