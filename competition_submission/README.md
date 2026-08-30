# 星火智学 XH-202620 比赛提交工作区

本目录只收敛比赛可见材料，不替代仓库中的技术文档与测试证据。所有`DRAFT`文件必须在真实用户、专家或团队签字完成后再改为最终版。

## 目录

| 目录 | 内容 | 当前状态 |
|---|---|---|
| `00-提交清单/` | 材料状态、责任人与最终门禁 | DRAFT |
| `02-伦理与安全/` | 伦理、安全、AI标识和责任边界 | DRAFT，待团队签字 |
| `03-Demo/` | 本地启动、离线备份与演示检查 | DRAFT |
| `04-作品方案/` | Guizang网页PPT与PPTX预览 | 已生成DRAFT |
| `06-效果验证/` | 170秒视频脚本、专家/用户表、效果报告 | DRAFT，真实证据待填 |

`04-作品方案/guizang-tech-v2/`为不覆盖旧稿的技术主线V2：12页瑞士IKB网页PPT、PowerPoint回渲染审计和1.35MB PPTX，叙事改为数据治理→Evidence推理→LegalEduEval→Agent消融→四场景验证。ORCDF外展只保留一条受控同47题结论，不平铺三版本。

`06-效果验证/170秒技术主线视频脚本_V2_DRAFT.md`与`技术主线机器证据增量报告_V2_DRAFT.md`同步新证据；当前121.6秒视频仍是旧叙事DRAFT，未冒充已完成V2录制。

本地`offline_backup/final-demo/`已生成但不进入Git：它含演示密码哈希，仅供团队离线保管。可公开的去标识审计摘要为`03-Demo/FROZEN_DEMO_AUDIT.json`，源备份与空目录恢复各24项语义检查均通过。

已基于恢复库录制5段真实浏览器素材并合成65.2秒无声预演：原始视频继续留在Git忽略目录；公开时长、SHA、分辨率和0错误门禁见`03-Demo/VIDEO_SEGMENTS_AUDIT.json`。该预演不是最终配音成片，也不替代用户/专家证据。

另生成121.6秒、1920×1080、中文字幕、AI配音DRAFT，已包含Evidence-KT、ORCDF、七步路径、Model Adapter、可信RAG、教师HITL、多智能体以及去标识INV/PR形成性审计；公开审计见`03-Demo/NARRATED_VIDEO_DRAFT_AUDIT.json`。10段旁白最大语速1.037倍，未检出超过1.2秒静音，全程标识“AI配音·DRAFT”；最终提交前仍须团队完整审片并决定保留AI配音或替换真人旁白。

## 不得删除的证据边界

- MOOCCubeX民法/宪法ORCDF是`shadow/实验`，不是刑法课堂实时掌握率。
- mastery未校准，不称“掌握概率”。
- 当前模型是OpenCode/DeepSeek基线；微调端点为`not_connected`，不称已完成LoRA/SFT。
- 三题自动门禁3/3不等于法学专家准确率；专家结论仍为`pending`。
- 浏览器smoke与固定E2E证明软件链路，不证明学习增益或用户认可。
