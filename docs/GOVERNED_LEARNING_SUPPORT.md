# 受治理AI分层解惑

切片G把学生困惑从“只影响推荐排序”扩展为两步形成性辅导：系统先要求学生说出自己的理解，再基于当前KnowledgeCard、公开TaskItem和标准Evidence生成分层解释。

## 两步会话

1. 学生先通过`confusion_annotation`把困惑归入证据账本；
2. `POST /api/learning-support/sessions`建立学生私有会话，确定性生成诊断追问；
3. 学生回答追问后调用`POST /api/learning-support/sessions/{id}/respond`；
4. 返回“规范原文—白话解释—事实适用—争议边界—下一动作”；
5. 会话只写`learning_support_sessions`，不生成LearningEvent、不更新LearnerProfile或正式成绩。

同`session_id`同payload幂等，同ID改内容409；会话只允许创建者访问，其他学生403。KnowledgeCard/TaskItem版本随会话保存，旧页面不能悄悄改用新内容。

## Evidence门禁

模型任务使用统一路由`learning_support`，可单独灰度约10B微调模型。提示只提供：

- 当前受治理KnowledgeCard；
- 当前公开TaskItem（不含私有答案/解析）；
- KnowledgeCard的标准Evidence原文；
- 学生困惑、诊断追问和学生回答。

学生文本被明确视为待分析内容，其中的指令不得执行。模型必须输出合法JSON，且`norm.citations`必须同时满足：

- 条号存在于当前受治理法源；
- quote是该条文的逐字片段；
- 引用属于当前KnowledgeCard标准Evidence集合。

任何JSON、结构、条号、逐字片段或Evidence范围门禁失败，都自动切换为确定性KnowledgeCard fallback，不把坏模型输出展示给学生。通过门禁仍只代表“存在与逐字片段正确”，不自动证明法条语义蕴含学生结论。

## 低置信度与教师边界

- 模型`confidence < 0.65`时自动`teacher_review_required=true`；
- 模型可以主动标记争议需要教师复核；
- deterministic fallback始终需要教师复核；
- 页面明确显示形成性、不计分、不更新掌握、不能替代教师结论。

真实联调中，OpenCode主路由`deepseek-v4-flash`两次输出均通过标准Evidence门禁：一次置信度0.9完成，一次0.6自动进入教师复核；每次引用1条有效逐字Evidence，学生LearningEvent/画像事件数均未增加。

## 学生界面

困惑便笺保存成功后出现“开始分层解惑”。专用Socratic批注页展示：

- 三步进度：记录困惑、诊断追问、分层解释；
- 学生自己的困惑和诊断问题；
- 四层解释与可见法条引文；
- governed AI或deterministic fallback来源；
- 下一步回到任务、复习知识卡或询问教师。

页面不是自由聊天框，学生必须先回答诊断追问，才能得到解释。

## 本地验证

快速浏览器smoke默认不调用模型。启用真实解惑门禁：

```powershell
$env:JOURNEY_TEST_SUPPORT='1'
cd frontend
npm run smoke:journey
```

脚本验证4层解释、Evidence显示、全旅程、私有字段和console/page/HTTP/request错误，并保存分层解惑截图。真实模型调用依赖本地配置；模型失败时确定性fallback仍应使旅程通过。

## 当前缺口

- 尚无教师端低置信度会话复核队列和复核结果回传；
- 只覆盖10个课程核心知识点与选择任务，未覆盖主观短答；
- 没有真实学生对解释可理解性、纠错效果或保持迁移的验证；
- 通过引用门禁不等于法律语义蕴含或争议观点正确。
