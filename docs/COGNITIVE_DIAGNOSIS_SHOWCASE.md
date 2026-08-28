# 认知诊断、ORCDF shadow与个性化路径展示

比赛展示版在学生顶部新增“认知诊断”入口，将原本分散的在线画像、实验结果、路径规划和模型路由组织成一个可在3分钟视频中连续展示的驾驶舱。

## 四个视图

### 1. 在线诊断

在线主链路仍使用Evidence-KT/V0保守证据画像：

- 10个刑法核心知识点的最新状态、LearningEvent数和证据置信状态；
- 当前学生自己的去标识化事件时间线；
- 重复错误标签与困惑信号；
- 自适应策略版本、合格事件数、已观察知识数和证据不足数。

`GET /api/adaptive/evidence-timeline`只返回当前登录学生的事件ID、类型、阶段、任务、时间、知识判定、错误标签、标准Evidence ID和长期画像资格，不返回回答原文、邮箱或`source_response_sha256`。

状态口径：

- `insufficient_evidence`：没有足够独立证据；
- `provisional`：至少3个合格事件且覆盖2道不同任务；
- 困惑是学生自报信号，只改变推荐优先级，不直接降低掌握；
- 所有状态均不是经过刑法课堂外部校准的掌握概率。

### 2. ORCDF SHADOW

展示数据来自真实训练产物，而不是前端随机数：

| 版本 | 范围 | Q矩阵 | 主范围AUC | 同47题AUC |
|---|---|---|---:|---:|
| V0 | 1,256题、126,073作答 | 180原始exercise_id | 0.9316 | 0.7272 |
| V1 | 590可训练题、124,121作答 | 74个`llm_provisional`概念、741 Q边 | 0.9377 | 0.7489 |
| V2 | 47题、7,356作答 | 97教师知识点、105 Q边 | 0.7528 | 0.7528 |

同47题seed42学生聚类bootstrap同时展示：V1-V0差0.0299，95%CI `[0.0037, 0.0537]`；V2-V0的CI跨0；V2-V1为-0.0184。页面明确：三个主范围不同，不能用主范围AUC证明Q矩阵优劣。

6×8热力图是V2 seed42 `mastery.npy`的真实切片。值集中在0.5附近且未校准，只能称为模型相对状态。静态展示快照保存以下来源SHA：

- `analysis_final/summary.json`：`811abb3fad273bf27711444a0fb715519ac24b30d752f0db58d695519a91a9d5`
- V2 seed42 `mastery.npy`：`e27d830486ceb1ad81370957855b73e46a571144bce9d8733afe30a47379d0dc`
- V2数据manifest：`8df29047c41225f7662a67a35c2a024cd39642072040c5e5016f9a6a917c05f2`

这些行为来自MOOCCubeX民法/宪法课程，不是当前本科刑法课堂。新刑法课堂只能使用通用层初始化并与scratch对照，禁止按数组位置迁移旧学生、题目、知识点或题目参数。

### 3. 个性化路径

页面从当前第一推荐知识点动态组织七步路径：诊断薄弱点、必要时回退先修、选择TaskItem、主观短答、CaseBundle案件、角色互换，以及根据下一条LearningEvent重新计算间隔复习。

节点来自当前KnowledgeCard、Recommendation、SubjectiveTask和CasePicker，不是写死的“最优路径”。算法负责排序；大模型只解释或执行任务。完成按钮直接回到现有自主学习卷宗。

### 4. 模型路由

模型页读取脱敏`GET /api/model/catalog`，显示`subjective_scoring`、`learning_support`、`teaching_judge`和`response_assist`。

当前基线模型、provider与端点主机按真实配置显示；API Key和URL私有路径不进入响应。没有配置`SIMLAW_SMALL_MODEL_*`时显示“微调端点已预留·当前未连接”和`not_connected`，不得宣称完成LoRA/SFT。

四段对比路线固定为基础模型→Prompt/Few-shot→可信RAG→RAG+微调。未来接入通过独立金标准的模型只替换任务路由，不修改学生页面。

## 可复现浏览器验证

启动本地SQLite+adaptive+Vite后：

```powershell
cd frontend
npm run smoke:cognitive
```

脚本真实注册学生，完成1次选择题与1次困惑，再依次打开四个视图。比赛主视口1500×980结果：10个知识点、2条事件、3个ORCDF版本、48个真实热力格、7个路径节点、4个模型任务路由；私有字段、console/page/HTTP/request错误均为0。

四张截图写入Git忽略的`.codex-artifacts/cognitive-*/screens/`，可直接作为PPT和录屏构图参考。

## 比赛映射

- **视频第2段（15—45秒）**：在线Evidence-KT与ORCDF shadow；
- **视频第3段（45—70秒）**：七步路径和“进入当前推荐任务”；
- **视频第7段（155—170秒）**：Model Adapter与微调`not_connected`边界；
- **PPT第5/6/7/10页**：在线诊断、ORCDF、路径、模型路由；
- **评分项**：技术实现20、技术先进10、创意实用20、完成度10。

仍需真实证据：当前页面和冒烟证明软件机制可运行，不证明刑法掌握校准、路径学习增益或用户认可；至少2名真实目标用户和3题准确性报告仍须单独完成。

