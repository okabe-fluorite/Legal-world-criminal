# Hybrid RAG Corpus V1 机器审计

- 快照日期：`2026-09-02`
- 构建器：`hybrid-rag-corpus-builder-v1`
- 物理候选源：**2,024**
- canonical文档：**2,024**；重复源：**0**
- 法律/法规/司法/案例块：**54,463**
- 案例语义父段/检索子块：**1,591 / 1,599**
- 教材解释块：**1,404**
- 题目public/private：**1,184 / 1,184**

## 检索契约

`BM25F + Qwen3-Embedding-8B → RRF → Reranker → 权威/时效/Evidence门禁`。
Reranker失败降级RRF；Embedding失败降级BM25F；明确条号命中不可被语义排序挤掉。

## 确定性门禁

- [x] `source_accounting_exact`
- [x] `canonical_document_ids_unique`
- [x] `inventory_metadata_all_or_none`
- [x] `legal_chunk_ids_unique`
- [x] `case_parent_ids_unique`
- [x] `case_children_all_have_parent`
- [x] `case_parent_child_document_match`
- [x] `non_case_chunks_have_no_parent`
- [x] `textbook_chunk_ids_unique`
- [x] `all_chunks_nonempty`
- [x] `question_public_private_ids_match`
- [x] `question_public_private_keys_absent`
- [x] `question_private_embedding_disabled`
- [x] `absolute_paths_absent`
- [x] `model_network_calls_zero`
- [x] `schema_validation_passed`

## 证据边界

canonical and chunk artifacts are retrieval candidates; they do not establish current legal validity, semantic entailment, teacher approval, or learning effects
本阶段Embedding/Reranker/模型/网络调用均为0；该产物证明canonical、分块与答案隔离，不是混合检索效果。
