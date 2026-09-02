# 任务计划：法律/教材/题目混合RAG

## 目标
先制定计划，再按确认后的阶段实现法律全库混合检索、教材解释RAG和题目相似检索。法律Dense Embedding使用EduBrain现有SiliconFlow配置，并在融合候选后使用Reranker；当前不调用API、不修改业务代码。

## 当前阶段
阶段3：qrels与NLI人工模板（进行中）

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
- [ ] 100—200条检索qrels
- [ ] 180对NLI三分类标注模板
- [ ] 冻结指标和分组
- **状态：** pending

### 阶段4：SiliconFlow小样本探针
- [ ] 200—500块API调用（Embedding + Reranker最小探针）
- [ ] 核验URL、模型、1024维、批量、费用、延迟、重试
- [ ] API失败不影响BM25F
- **状态：** pending

### 阶段5：三库向量索引
- [ ] legal_authority
- [ ] textbook_explanation
- [ ] question_public/question_private
- [ ] float16 NPY+metadata+manifest+断点续跑
- **状态：** pending

### 阶段6：Hybrid集成
- [ ] BM25F+Dense并行
- [ ] RRF融合和精确条号保护
- [ ] Reranker对RRF候选重排；失败时降级RRF
- [ ] EvidencePack与feature flag
- [ ] BM25F fallback
- **状态：** pending

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

## 错误记录
| 错误 | 次数 | 处理 |
|---|---:|---|
| PowerShell复杂foreach/内嵌if解析失败 | 3 | 改为多行、先计算变量、再收集rows |
| 首次大补丁预期active plan名称不一致 | 1 | 不覆盖现有technical plan，改为独立计划目录和文档 |
| 首次真实构建出现1个重复chunk_id | 1 | `重新组建仲裁机构方案`内部同一第二条重复；保留原文并把section_index纳入稳定ID，不放宽唯一性门禁 |
