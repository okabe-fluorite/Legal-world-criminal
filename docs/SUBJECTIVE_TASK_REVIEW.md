# 主观短答、角色互换与教师复核

切片H把预习/复习从确定性选择题扩展到13个受治理主观任务：10个核心知识点短答和3个CaseBundle角色互换任务。模型只提供形成性修改建议；任何主观分数、知识判定和长期画像证据都必须经过任课教师批准。

## 对象与内容来源

`schemas/subjective-task-v1.schema.json`冻结独立`SubjectiveTask`契约，生成数据位于：

- `adaptive_service/data/subjective_tasks.jsonl`：13个任务；
- `adaptive_service/data/subjective_task_manifest.json`：数量、源版本和文件哈希；
- `backend/scripts/build_subjective_tasks.py`：从10个KnowledgeCard和3个CaseBundle重建任务。

选择题继续使用`TaskItem + exact_option_set`确定性判分；主观题不混入该接口，避免把LLM评分伪装成客观正确率。公开任务包含题干、公开情境、知识/能力、字数要求、标准Evidence ID及法条名称/条号，不包含：

- `rubric_private`：维度、权重和评分锚点；
- `expected_points_private`：教师预期要点、典型错误和参考边界；
- 标准答案或可直接复制的完整论证。

首批任务状态只表示受治理试点内容，不表示已经取得真实课堂难度、区分度或学习增益参数。每学期仍需刑法教师复核有效法与教学口径。

## 学生流程

学生从“自主学习→进入主观论证与角色互换”完成：

1. 选择知识短答或案例角色互换任务；
2. 查看公开情境、可引用法条与字数门槛；
3. 提交80—1200字论证和1—5级自评把握度；
4. 系统核验学生引用是否属于任务标准Evidence；
5. 模型按私有Rubric返回优点、修订点和建议改写，或主动弃权；
6. 页面只显示“形成性参考、等待教师复核、不更新掌握或正式成绩”。

同`attempt_id`同payload幂等，同ID改内容409；过期任务哈希422；跨学生读取403。

## 模型与Evidence门禁

模型任务名为`subjective_scoring`，可以单独灰度到约10B微调模型。模型只接收当前任务、私有Rubric/预期要点、标准Evidence和学生原文，并必须返回结构化JSON。

以下任一情况都会弃权，`ai_score=null`：

- JSON或Rubric结构不合法；
- 模型置信度低于0.72或主动弃权；
- 学生没有使用任务允许的有效法条引用；
- 模型声称使用了任务标准集合之外的Evidence ID；
- 模型调用失败或超时。

即使模型置信度高、引用门禁通过，尝试状态仍为`needs_teacher_review`，且`evidence_eligibility.long_term_profile=false`。引用门禁只证明条号存在、逐字原文和任务Evidence范围正确，不证明学生论证的法律蕴含或结论无争议。

## 教师流程与权限

教师驾驶舱第三页“主观复核”只返回任课教师自有有效班级中的已选课学生。队列包含匿名`student-ref`、学生原文、任务/知识点、AI弃权和置信度、引用门禁及形成性建议；不返回邮箱或原始用户ID。

教师可以：

- `approve`：必须给0—1教师分并选择`mastered/partial/missing`；
- `request_revision`：退回学生修订，不生成画像证据；
- `reject`：拒绝本次稿件，不生成画像证据。

只有`approve`生成`teacher_reviewed_subjective_assessment`。事件绑定任务版本、学生回答哈希、教师复核ID、标准Evidence、能力分、知识判定和错误标签，标记`long_term_profile=true`后投递adaptive；同复核ID同payload幂等，同ID改内容409。其他教师不能查看或批准非自有班级学生。

这仍是形成性课堂证据，不是正式课程成绩。正式计分还需要院校授权、课程考核规则、双评/仲裁和申诉机制。

## API

| 方法与路径 | 用途 |
|---|---|
| `GET /api/subjective-tasks/catalog?phase=prestudy|review` | 13个任务的公开投影 |
| `GET /api/subjective-tasks/{task_id}` | 单任务公开投影 |
| `POST /api/subjective-attempts` | 学生提交并获得AI形成性反馈/弃权 |
| `GET /api/subjective-attempts/{attempt_id}` | 学生读取自己的尝试 |
| `GET /api/teacher/subjective-attempts` | 教师自有班级匿名待办队列 |
| `POST /api/teacher/subjective-reviews` | 教师批准、退回或拒绝 |

## 已验证证据

确定性机制审计固定网络0、LLM 0、课堂记录0，验证：

- 13任务=10知识短答+3角色互换；
- 公开任务不含Rubric/预期要点，均提供公开Evidence索引；
- 高置信度模型候选仍不产生LearningEvent或LearnerProfile；
- 越界Evidence ID强制弃权；
- 教师队列无邮箱/原始用户ID；
- 教师批准后才生成且仅生成一条长期画像合格事件。

本地真实浏览器旅程还验证学生提交→模型反馈/弃权→教师建班选课→匿名复核→批准→队列清零→班级事件从2变3，桌面1500×980和窄屏780×900均通过，隐私、console/page/HTTP/request错误为0。真实OpenCode `deepseek-v4-flash`样本中，一次置信度0.80并通过1条标准Evidence，另一次模型弃权；两种分支都必须等待教师。

## 当前缺口

- 13题没有真实学生作答参数，不能据此证明难度、区分度或知识追踪增益；
- 当前教师审批为单评，没有双评一致性、仲裁、成绩发布和申诉；
- 主观任务作为独立入口，尚未纳入推荐器的间隔调度与路径A/B实验；
- 尚无真实本科刑法课堂对反馈可理解性、修订质量、保持和迁移的验证；
- 角色互换仅覆盖3个发布案例，案例与司法解释Evidence仍需继续扩充。
