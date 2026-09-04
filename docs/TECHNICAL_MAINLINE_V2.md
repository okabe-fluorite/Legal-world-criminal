# 星火智学刑法学科技术主线 V2

## 技术链

```text
4,173混合文件
→ 2,024份官方canonical材料逐份来源记录与轻量效力元数据
→ 57,051条词法/语义混合检索记录
→ 多来源分层EvidencePack（813条刑法课程核心规范基线）
→ 课程知识图 × Hybrid RAG × 结构化法律推理
→ 确定性Gate与教师闸门
→ LegalEduEval模型无关评测
→ 可信问答 / 案件Agent / 主观诊断 / 个性化路径
```

## 当前机器成果

| 里程碑 | 核心产物 | 当前结论 |
|---|---|---|
| 数据治理 | `data_governance/*` | 2,024/2,024对应官方原件；1,045当前有效、598历史、5被替代、13废止、363效力未完全核实 |
| Hybrid RAG | 57,051条三类索引 + R0—R4 | R4候选Recall@5 0.86、无答案误返回0；教师qrels复核仍为0 |
| Graph × RAG | 10节点/10先修边 + `knowledge_context` | 知识点/条号/先修扩展检索，Evidence反向支撑诊断解释和下一任务 |
| 2024刑法版本 | `CRIMINAL_LAW_2024_VERSION_AUDIT` | 年份与修正案十二正确；具体合并文件不能直接准入 |
| Evidence推理 | `legal-reasoning-v1.schema.json` + Gate | 1正例/6负例按预期；只证明确定性纪律 |
| LegalEduEval | 100题Schema/Runner/Dataset Card | 候选not_gold；E0—E3与教师审核pending |
| Agent消融 | `AGENT_ABLATION_V1` | 反方2→3，同时耗时×5.7753、token×2.7167；教师盲评pending |
| 认知诊断 | Evidence-KT + ORCDF shadow | 正式产品使用保守事件画像；ORCDF只作民法/宪法实验 |
| 2D导师与语音 | 4态WebP + 讯飞IAT/TTS | 三个导师场景、可下载TTS WAV、真实ASR转写；不是Live2D/讯飞数字人 |

## 对外ORCDF选择

内部保留V0/V1/V2完整对比。PPT/视频只展示同47题seed42的`V1−V0=+0.02994`、95%CI `[0.00372,0.05366]`，并同时显示：MOOCCubeX民法/宪法、LLM-Q provisional、mastery未校准、不进入刑法正式画像。

## Qwen3-8B接口

模型训练由队友负责。业务仅依赖OpenAI-compatible Adapter；交付前E3保持`pending_model_delivery`。接入需要API/模型名、模型卡、基座与LoRA配置、训练manifest、日志、许可证、独立评测及部署指标。401、模型名或参数错误不得静默回退。

## 证据等级

- 已有：较强L1软件机制证据与候选L2审核准备。
- 待补：100题教师Gold、Agent双教师盲评、2名目标用户、伦理签字、队友模型独立评测。
- 不具备：刑法课堂掌握概率校准、路径因果效果、正式成绩自动评分证据。

## 比赛材料

- 技术主线PPT：`competition_submission/04-作品方案/星火智学_作品方案_技术主线V2_DRAFT.pptx`。
- 网页源：`competition_submission/04-作品方案/guizang-tech-v2/index.html`。
- 视频脚本：`competition_submission/06-效果验证/170秒技术主线视频脚本_V2_DRAFT.md`。
- 机器证据报告：`competition_submission/06-效果验证/技术主线机器证据增量报告_V2_DRAFT.md`。

## Demo技术证据路线

登录后点击顶部“技术证据”：

1. 数据治理：4,173→2,024→57,051；813条明确为刑法课程核心规范基线；
2. 推理/评测：11项Gate、1正例/6负例、LegalEduEval 100题；
3. Agent/边界：要件4/4、反方2→3、耗时/token成本与教师盲评pending。

页面由后端实时读取审计SHA，详见`docs/TECHNICAL_EVIDENCE_SHOWCASE.md`。

真实人员材料没有被代填；最终提交包须等待上述pending项完成后再重建。
