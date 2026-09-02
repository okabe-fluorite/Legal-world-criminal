# 任务计划：法律/教材/题目混合RAG

## 目标
先制定计划，再按确认后的阶段实现法律全库混合检索、教材解释RAG和题目相似检索。法律Dense Embedding使用EduBrain现有SiliconFlow配置，并在融合候选后使用Reranker；当前不调用API、不修改业务代码。

## 当前阶段
阶段7：评测与材料（进行中）

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
