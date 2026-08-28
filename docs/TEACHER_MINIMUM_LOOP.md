# 教师端最小闭环

切片D提供教师角色、班级、选课、匿名形成性聚合和内容复核台账。它的目标是让本科刑法教师能看到“全班卡在哪里、哪些内容需复核”，不是做学生排名或自动成绩系统。

## 角色授权

普通注册始终是`student`，浏览器不能在注册或请求中自报`teacher/admin`。教师身份只通过以下显式运维方式授予：

1. 本地或部署环境设置逗号分隔的`SIMLAW_TEACHER_EMAILS`/`SIMLAW_ADMIN_EMAILS`白名单；
2. 对已注册账号运行本地管理脚本：

```powershell
$env:DATABASE_URL='sqlite+pysqlite:///D:/path/to/legalworld-local.db'
uv run --isolated --with-requirements requirements.lock.txt -- python `
  backend\scripts\grant_user_role.py `
  --email teacher@school.edu `
  --role teacher
```

授权记录保存在`user_roles`，包含`granted_by`。环境白名单优先于数据库角色，适合本地演示和部署初始化；生产应由受控运维系统管理，不能暴露为公共API。

班级细分默认最少需要3名学生（`SIMLAW_TEACHER_MIN_AGGREGATE_SIZE=3`）。不足时仍可显示班级人数和事件总数，但知识、能力和错误细分全部抑制。降低阈值只用于隔离的本地功能测试，不应作为真实课堂默认配置。

## 数据对象

- `course_classes`：教师拥有的课程班级，包含课程、学期、名称和状态；
- `class_enrollments`：已注册学生与班级的显式关系；
- `content_review_events`：教师对冻结KnowledgeCard/TaskItem的不可变复核事件；
- 现有`learning_events`与`learner_profiles`：班级学情的事实源，不复制第二套学习数据。

## API与权限

所有`/api/teacher/*`接口都要求登录且角色为teacher/admin。

| 方法与路径 | 用途 | 边界 |
|---|---|---|
| `GET /api/teacher/overview` | 当前教师的班级列表 | teacher只返回自己拥有的班级；admin可见全部 |
| `POST /api/teacher/classes` | 建立班级 | 同教师/课程/学期/名称幂等 |
| `POST /api/teacher/classes/{id}/enrollments` | 加入已注册学生 | 返回班内稳定匿名`student-ref`，不回传邮箱 |
| `GET /api/teacher/classes/{id}/analytics` | 班级形成性聚合 | 只查询自有班级；不返回学生邮箱或困惑原文 |
| `GET /api/teacher/reviews/catalog` | 10卡/30任务公开复核目录 | 使用公开TaskItem投影，不含私有答案 |
| `GET /api/teacher/case-bundles/{id}` | 3个案例的教师参考投影 | 仅teacher/admin；含指导要点与阶段教师参考 |
| `POST /api/teacher/reviews` | 写不可变审核决定 | 同ID同payload幂等，同ID改内容409，旧内容版本422 |
| `GET /api/teacher/reviews/audit` | 当前教师审核台账 | 不覆盖或删除既有事件 |

## 班级学情口径

教师页面只展示：

- 班级人数、发生学习行为人数、事件/TaskAttempt/案例阶段/困惑数量；
- 知识点`mastered/partial/missing/provisional`学生数和困惑计数；
- 有证据学生的能力均值与高频错误标签；
- 数据边界、样本局限与禁止排名说明。

当班级人数低于最小聚合阈值时，后三类细分不返回数据，以避免“匿名但可被小班反推”。

困惑原文可能包含敏感信息，因此只聚合每知识点数量。当前最小版本不提供学生名单、单人钻取或排行榜；学生加入成功只显示班内哈希`student-ref`。

`provisional`仍是至少3个合格事件/2道任务形成的临时状态，不是校准掌握概率。所有聚合均为形成性证据，不能自动转为正式成绩。

## 内容复核

教师可对CaseBundle、KnowledgeCard或TaskItem提交：

- `approve`：同意当前版本在本学期低风险试用；
- `request_revision`：要求回到治理流水线修订后复核；
- `reject`：停止使用当前版本。

审核事件绑定`object_version`哈希。提交只新增覆盖记录，不直接改写冻结JSON；真正修订必须更新教师决策/法源/题库，重新运行受治理构建器、Schema与回归测试。这避免教师页面绕过版本、哈希和答案隔离。

## 教师页面

角色为teacher/admin时，顶部显示“教师驾驶舱”：

- “班级学情”页支持建班、加入学生、班级指标、知识补强信号、能力均值与错误标签；
- “内容复核”页支持知识卡/任务筛选、版本与Evidence数量检查、教师决定与复核意见；
- 页面不展示学生邮箱、困惑原文或题目私有答案。

## 本地验证

设置独立测试教师白名单并启动本地SQLite栈后：

```powershell
$env:SIMLAW_TEACHER_EMAILS='teacher-smoke@example.com'
$env:SIMLAW_TEACHER_MIN_AGGREGATE_SIZE='1' # 仅本地单人功能测试
uv run --isolated --with-requirements requirements.lock.txt -- python start.py

cd frontend
$env:TEACHER_SMOKE_EMAIL='teacher-smoke@example.com'
npm run smoke:teacher
```

浏览器冒烟会自动：注册学生→完成一次TaskAttempt和困惑→退出→注册白名单教师→建班→加入学生→核对匿名指标→写内容复核事件→扫描隐私与控制台/网络错误，并保存班级学情和内容复核截图。

## 当前缺口

- 没有院校统一身份、教务课程同步、退课/调班审批和多教师协作；
- 没有“强制困惑标注”课堂门禁或匿名原文的合规查看流程；
- 没有教师对主观题的复核队列、双评一致性与正式成绩发布；
- 没有真实班级试点数据、路径干预实验或面向不同院校的隐私阈值验证。
