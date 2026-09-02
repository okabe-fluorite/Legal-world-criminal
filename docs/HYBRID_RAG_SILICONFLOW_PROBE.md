# Hybrid RAG SiliconFlow真实探针

2026-09-02已完成一次分层真实调用。该结果用于证明Embedding与Reranker接口、维度、批量处理、排序和用量记录可以工作，不等同于教师标注后的正式检索准确率。

## 结果

| 项目 | 真实结果 |
|---|---|
| Embedding模型 | Qwen/Qwen3-Embedding-8B |
| Embedding样本 | 300块，六类各50块 |
| Embedding请求 | 19次，全部成功 |
| 向量 | 1024维，300/300为有限值 |
| Embedding延迟 | p50 1.184秒；p95 4.332秒 |
| Reranker模型 | Qwen/Qwen3-Reranker-8B |
| Reranker样本 | 30个查询，每个8个候选，返回Top 5 |
| Reranker请求 | 30次，全部成功 |
| Reranker延迟 | p50 0.606秒；p95 1.161秒 |
| API端点 | SiliconFlow国内官方端点 |
| 调用错误 | 0 |

六类Embedding样本分别来自法律、行政法规、司法解释、案例检索子块、教材解释层和公开题目层。案例继续采用父子分段：短子块参与召回与重排，命中后回填完整语义父段。

## 候选行为

自动生成的待复核qrels中，30个查询的候选正例均进入Top 1和Top 5。由于这些qrels尚未经过法学教师逐条复核，该数字只能用于发现接口或排序异常，不能称为正式Recall、NDCG或专家准确率。

## 降级设计

- Reranker失败：继续使用RRF融合顺序；
- Embedding失败：继续使用BM25F；
- 明确法名和条号命中：进入精确匹配保护，不被纯语义排序挤掉；
- API密钥、Authorization和输入正文不进入公开报告或用户界面。

## 参考协议

- [SiliconFlow Embedding API](https://api-docs.siliconflow.cn/docs/api/embeddings-post)
- [SiliconFlow Rerank API](https://api-docs.siliconflow.cn/docs/api/rerank-post)

## 证据边界

当前完成的是API兼容性和300块分层探针。教师Gold qrels、完整索引、BM25F/Dense/RRF消融和端到端回答质量仍属于后续阶段。
