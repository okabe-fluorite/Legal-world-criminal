# 预习与复习TaskAttempt契约

切片B让切片A发布的TaskItem真正可完成：学生在预习或复习阶段提交答案，adaptive服务使用私有答案确定性判分，生成不可变LearningEvent，更新保守证据画像并返回下一任务。困惑标注使用独立事件，不伪装成答错证据。

## 对象与接口

### TaskAttempt

Schema：`schemas/task-attempt-v1.schema.json`

浏览器调用登录态backend：

```http
POST /api/adaptive/attempts
Authorization: Bearer <student token>
Content-Type: application/json
```

```json
{
  "schema_version": "criminal-law-task-attempt-v1",
  "attempt_id": "web-20260827-0001",
  "task_id": "GEN_...",
  "content_version": "64位TaskItem内容哈希",
  "phase": "prestudy",
  "selected_options": ["A"],
  "submitted_at": "2026-08-27T08:00:00+08:00",
  "response_time_ms": 12500,
  "confidence": 4,
  "hint_count": 0,
  "answer_revealed_before_submit": false
}
```

backend以JWT登录用户ID覆盖任何浏览器提供的`student_pseudonym`，再调用adaptive的`POST /attempts`。服务端检查：

- `task_id`存在且允许当前`prestudy/review`阶段；
- `content_version`与当前TaskItem哈希完全一致，过期页面不能静默答旧题；
- 选项来自该题且不重复；
- `submitted_at`是带时区的ISO-8601时间；
- 判分规则为TaskItem冻结的`exact_option_set`。

### ConfusionAnnotation

Schema：`schemas/confusion-annotation-v1.schema.json`

```http
POST /api/adaptive/confusions
Authorization: Bearer <student token>
Content-Type: application/json
```

```json
{
  "schema_version": "criminal-law-confusion-annotation-v1",
  "annotation_id": "web-confusion-0001",
  "phase": "review",
  "task_id": "GEN_...",
  "knowledge_id": "",
  "confusion_type": "fact_application",
  "note": "我不确定规范条件如何适用于这一事实。",
  "request_help": true,
  "submitted_at": "2026-08-27T08:05:00+08:00"
}
```

必须提供`task_id`或稳定`knowledge_id`。若二者都提供，服务端会核验映射一致。困惑事件进入画像的`confusions`与推荐上下文，但`evidence_eligibility.long_term_profile=false`，不会直接把知识状态降为`missing`。

## 幂等与不可变语义

- 客户端生成并在重试时复用`attempt_id`或`annotation_id`；
- adaptive将`学生ID + 客户端ID + 事件类型`稳定映射为`event_id`；
- 同ID、同完整payload重复提交返回`duplicate`，数据库事件数不增加；
- 同ID改变答案、时间或其他字段返回HTTP 409，不覆盖原事件；
- backend再次以`event_id + payload_sha256`写入本地LearningEvent表，并拒绝adaptive返回的学生身份与JWT身份不一致；
- backend只持久化LearningEvent、画像、推荐和策略版本，不把`feedback.correct_options`或`feedback.rationale`写入adaptive响应快照。

## 判分、辅助与画像边界

TaskAttempt会生成`task_attempt_assessment`事件，包含学生选项、耗时、置信度、确定性分数、目标能力、知识证据、误概念标签、证据ID、任务版本和辅助信息。

- 正确：知识证据为`mastered`；错误：为`missing`；多选题部分命中时为`partial`；
- 难度进入能力证据权重，提示每次降低15%，最低保留0.25形成性权重；
- 学生声明提交前已查看答案时，仍给即时反馈，但事件不更新长期画像；
- `provisional`只表示保守临时状态，至少要求3个合格事件且覆盖2道不同任务；
- 即使达到门槛，也不是校准的ORCDF掌握概率，不能直接用于正式成绩；
- 当前选项判分无需LLM；未来主观题必须走Rubric、低置信度弃权和教师复核。

## 响应与答案隔离

推荐和公开TaskItem永远不含`answer_private`、`rationale_private`、`misconceptions_private`。只有完成服务端判分后，当前登录学生的响应才返回：

- 是否正确、得分与临时知识状态；
- 正确选项与教学解析；
- 命中的误概念；
- 更新后的画像和不含答案的下一任务。

这适合形成性练习，不是防作弊考试系统。正式考试需增加开放/截止时间、一次性授权、监考、延迟公布答案和教师成绩确认。

## 当前未覆盖范围

- 学生端知识地图、答题组件和连续页面旅程；
- 主观题、案例短答与教师复核队列；
- 困惑聚合的教师端页面与AI分层解惑；
- 间隔重复调度、真实题目参数、校准知识追踪和路径干预实验。
