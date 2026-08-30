# 星火智学刑法学科技术主线 V2

## 技术链

```text
4,173候选材料
→ 版本/来源/隐私/准入治理
→ 813正式规范法源 + 课程Evidence
→ EvidencePack与结构化法律推理
→ 确定性Gate与教师闸门
→ LegalEduEval模型无关评测
→ 可信问答 / 案件Agent / 主观诊断 / 个性化路径
```

## 当前机器成果

| 里程碑 | 核心产物 | 当前结论 |
|---|---|---|
| 数据治理 | `data_governance/*` | 813正式法源；L2/L3候选保持待法学/版权复核 |
| 2024刑法版本 | `CRIMINAL_LAW_2024_VERSION_AUDIT` | 年份与修正案十二正确；具体合并文件不能直接准入 |
| Evidence推理 | `legal-reasoning-v1.schema.json` + Gate | 1正例/6负例按预期；只证明确定性纪律 |
| LegalEduEval | 100题Schema/Runner/Dataset Card | 候选not_gold；E0—E3与教师审核pending |
| Agent消融 | `AGENT_ABLATION_V1` | 反方2→3，同时耗时×5.7753、token×2.7167；教师盲评pending |
| 认知诊断 | Evidence-KT + ORCDF shadow | 正式产品使用保守事件画像；ORCDF只作民法/宪法实验 |
| 2D导师 | 4态WebP + `AITutor.vue` | 三个允许场景与浏览器朗读可用；不是Live2D/讯飞数字人 |

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

真实人员材料没有被代填；最终提交包须等待上述pending项完成后再重建。
