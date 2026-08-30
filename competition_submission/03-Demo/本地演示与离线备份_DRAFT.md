# 星火智学本地演示与离线备份（DRAFT）

## 1. 演示环境

- Windows 10/11，Chrome或Edge。
- Python依赖由`requirements.lock.txt`冻结，前端依赖由`frontend/package-lock.json`冻结。
- 默认本地SQLite + adaptive + Vite，不使用Docker。
- 演示分辨率建议1500×980或1600×900，浏览器缩放100%。

## 2. 启动

在仓库根目录执行：

```powershell
uv run --isolated --with-requirements requirements.lock.txt -- python start.py --model-config "<仓库外安全路径>\model-groups.env"
```

模型配置文件放在仓库外，不录屏、不提交Git。OpenCode为优先端点，DeepSeek官方仅在瞬态故障时fallback。若只回放离线快照，可不触发新的模型调用，但必须在讲解中说明“真实E2E审计快照”。

该命令会持续占用第一个PowerShell窗口。以下健康检查、教师授权和浏览器录制均在第二个PowerShell窗口执行。

健康检查：

```powershell
Invoke-RestMethod http://127.0.0.1:8000/api/status
Invoke-RestMethod http://127.0.0.1:8010/health
Invoke-WebRequest http://127.0.0.1:5173
```

通过标准：三个请求均HTTP 200；backend/adaptive响应显式为可用状态；前端返回HTML。若只“有返回”但状态字段异常，不得继续录制。

## 3. 演示账号准备

禁止使用真实学生邮箱。建议在最终演示数据库中准备两个虚构账号：

| 角色 | 账号 | 密码 | 准备方式 |
|---|---|---|---|
| 学生 | `[由团队填写虚构邮箱]` | `[团队现场保管]` | 页面注册后完成选择题、困惑、主观修订和case3快照 |
| 教师 | `[由团队填写虚构邮箱]` | `[团队现场保管]` | 页面注册后运行`backend/scripts/grant_user_role.py`显式授予teacher |

密码和Token不得写入本文件的最终公开版。教师账号需建立演示班级并加入学生账号；真实提交前人工检查页面不显示原始邮箱或内部ID。

教师授权命令（账号必须先在页面注册）：

```powershell
$repo = (Resolve-Path .).Path
$env:DATABASE_URL = "sqlite+pysqlite:///" + (($repo + "\backend\runtime\legalworld-local.db") -replace '\\','/')
uv run --isolated --with-requirements requirements.lock.txt -- python backend/scripts/grant_user_role.py --email "<教师演示邮箱>" --role teacher --granted-by competition-demo-operator
```

### 从全新库可复现生成冻结演示状态

以下流程不使用历史`backend/runtime`，创建只含`example.com`账号的独立工作目录。第一窗口启动：

```powershell
$repo = (Resolve-Path .).Path
$demo = $repo + "\competition_submission\offline_backup\final-demo-work"
if (Test-Path -LiteralPath $demo) {
  if (Get-ChildItem -LiteralPath $demo -Force | Select-Object -First 1) { throw "final-demo-work必须为空；请换新目录，不得混入旧状态" }
} else {
  New-Item -ItemType Directory -Path $demo | Out-Null
}
$env:DATABASE_URL = "sqlite+pysqlite:///" + (($demo + "\legalworld-local.db") -replace '\\','/')
$env:SIMLAW_ADAPTIVE_DB_PATH = $demo + "\adaptive.db"
$env:SIMLAW_SANDBOX_DATA_DIR = $demo + "\sandboxes"
$env:SIMLAW_TEACHER_EMAILS = "demo-teacher@example.com"
uv run --isolated --with-requirements requirements.lock.txt -- python start.py --model-config "<仓库外安全路径>\model-groups.env"
```

第二窗口先生成学生选择/困惑/主观退回—修订—批准和教师班级台账：

```powershell
cd frontend
$env:TEACHER_SMOKE_EMAIL = "demo-teacher@example.com"
$env:TEACHER_STUDENT_EMAIL = "demo-student@example.com"
$env:TEACHER_SMOKE_PASSWORD = "<团队现场保管的强密码>"
$env:TEACHER_CLASS_NAME = "刑法比赛演示班"
$env:TEACHER_RESULT_JSON = $demo + "\teacher-smoke-result.json"
npm run smoke:teacher
cd ..
```

再让同一学生账号运行case3真实E2E；冻结演示库本次耗时461.547秒，建议预留8—10分钟，输入是测试脚本固定回答，不是用户数据：

```powershell
uv run --isolated --with-requirements requirements.lock.txt -- python backend/scripts/run_player_e2e_smoke.py --case-id case_3 --email "demo-student@example.com" --password "<同一强密码>" --reuse-account --output competition_submission/offline_backup/final-demo-work/case3-e2e-summary.json
```

预期：教师队列清零，原稿保留退回决定、修订稿保留批准决定；同一学生拥有教师批准主观事件和case3 LC/INV/PR事件；case3 closed、runtime issue 0、Agent退场3。固定回答次数可能随Agent对话分支变化，必须以本次summary为准，不得写成用户人数。失败时不得冻结。

停止三个服务后，对冻结状态做自动语义审计：

```powershell
py competition_submission/scripts/audit_demo_state.py --runtime competition_submission/offline_backup/final-demo-work
```

只有`passed=true`才允许执行备份；审计同时检查两库完整性、只含`example.com`账号、教师退回/批准队列与事件、case3结案/退场/错误及固定输入披露。

## 4. 录制前验证

验证脚本会写入账号和事件，必须使用独立临时库，不能直接污染录制用冻结库。先在第一个窗口按`Ctrl+C`停止默认栈，并确认5173/8000/8010均不再监听；再启动临时栈：

```powershell
$preflight = (Resolve-Path .).Path + "\.codex-artifacts\competition-preflight"
New-Item -ItemType Directory -Force -Path $preflight | Out-Null
$env:DATABASE_URL = "sqlite+pysqlite:///" + (($preflight + "\legalworld.db") -replace '\\','/')
$env:SIMLAW_ADAPTIVE_DB_PATH = $preflight + "\adaptive.db"
$env:SIMLAW_SANDBOX_DATA_DIR = $preflight + "\sandboxes"
uv run --isolated --with-requirements requirements.lock.txt -- python start.py --model-config "<仓库外安全路径>\model-groups.env"
```

在第二个窗口执行：

```powershell
cd frontend
npm run build
npm run smoke:cognitive
npm run smoke:rag
npm run smoke:teacher
npm run smoke:case
```

`smoke:teacher`包含真实模型调用，耗时较长；`smoke:case`只验证比赛案件入口和审计标签，不重跑461.547秒完整E2E。通过范围包括console/page/HTTP/request错误0及脚本末尾的业务断言；教师闭环还需确认队列清零、事件2→3。

## 5. 离线备份

当前历史运行库含`edu.cn`域账号，隐私门禁会拒绝直接打包；必须先创建只含`@example.com`虚构账号的干净录制库。完成演练并停止三个服务后执行：

```powershell
py competition_submission/scripts/backup_demo_state.py --runtime competition_submission/offline_backup/final-demo-work --output competition_submission/offline_backup/final-demo
```

脚本使用SQLite backup API合并已提交WAL页，同时备份主库、adaptive库、sandboxes、case3脱敏E2E与三题JSON；非`example.com`账号会使操作失败。备份manifest含Git commit、文件大小和SHA-256，且明确数据库含演示密码哈希，只能团队离线保管。

## 三案例统一浏览器彩排

停止已经运行的本地服务后，可用同一个SQLite + adaptive + Vite栈顺序验证三条比赛演示路线：

```powershell
.\.venv\Scripts\python.exe -X utf8 competition_submission\scripts\run_three_route_rehearsal.py `
  --model-config "E:\guabangjieshuai\EduBrain\.env.example"
```

彩排包含：

1. 认知诊断、ORCDF shadow、七步路径、知识/论证图及Model/Media Adapter；
2. 三个典型问题、权威Evidence和2/2错误引用拒绝；
3. 主观稿进入教师门禁、退回原文修订、再次提交、批准后唯一画像事件。

机器结果写入`THREE_ROUTE_REHEARSAL_AUDIT.json/.md`；截图和服务日志写入Git忽略的`output/playwright/competition-rehearsal/`。彩排账号和学生输入均为合成演示数据，不能替代真实目标用户、独立法学专家或学习效果证据。

在另一空目录验证恢复，不覆盖当前运行库：

```powershell
py competition_submission/scripts/restore_demo_state.py --backup competition_submission/offline_backup/final-demo --target-runtime competition_submission/offline_backup/restore-check
```

确认恢复库可启动后，才复制到两个独立介质：

恢复验收命令（先确认默认栈已停止）：

```powershell
$restore = (Resolve-Path competition_submission/offline_backup/restore-check).Path
$env:DATABASE_URL = "sqlite+pysqlite:///" + (($restore + "\legalworld-local.db") -replace '\\','/')
$env:SIMLAW_ADAPTIVE_DB_PATH = $restore + "\adaptive.db"
$env:SIMLAW_SANDBOX_DATA_DIR = $restore + "\sandboxes"
uv run --isolated --with-requirements requirements.lock.txt -- python start.py --model-config "<仓库外安全路径>\model-groups.env"
```

在第二个窗口重跑三项健康检查，并用学生/教师账号各登录一次；确认事件数、教师台账和case3页面与冻结库一致后停止恢复栈。

停止恢复栈后，再对恢复目录运行同一个语义审计：

```powershell
py competition_submission/scripts/audit_demo_state.py --runtime competition_submission/offline_backup/restore-check --output competition_submission/offline_backup/restore-check/semantic-audit-restored.json
```

1. 固定Git提交与源码压缩包，不含`.env`、API Key、缓存和原始37GB数据。
2. `final-demo/`完整快照（主库、adaptive库、sandboxes和manifest）、PPTX、视频和本说明。
3. 本地813条法源与manifest；断网时可信RAG仍能做条号/逐字检索。
4. 浏览器预先打开登录页、认知诊断、可信RAG和网页PPT；关闭自动更新/通知。

备份完成后记录：

| 项 | 文件/目录 | SHA-256 | 复核人 | 日期 |
|---|---|---|---|---|
| 源码 | `[填写]` | `[填写]` | `[填写]` | `[填写]` |
| 演示数据库 | `[填写]` | `[填写]` | `[填写]` | `[填写]` |
| PPT | `[填写]` | `[填写]` | `[填写]` | `[填写]` |
| 视频 | `[填写]` | `[填写]` | `[填写]` | `[填写]` |

## 6. 现场降级

- 模型超时：展示明确标识的确定性fallback或预跑审计快照，不伪装为本次实时输出。
- 外部工具不可用：说明元典未配置/网络不可用，继续使用本地受治理法源。
- case3完整流程过长：回放379秒真实E2E关键节点，再现场运行短输入与引用核验。
- 任何页面出现HTTP/console错误：停止录制，切到离线备份；不得剪辑成“实时成功”。
- “0错误”仅指脚本覆盖的console/page/HTTP/request错误及结案后3秒观察窗口；不外推到未执行功能。

## 7. 真实浏览器视频素材

使用恢复库启动本地栈后，在第二个PowerShell设置仅本次进程可见的环境变量：

```powershell
$env:DEMO_STUDENT_EMAIL = "demo-student@example.com"
$env:DEMO_TEACHER_EMAIL = "demo-teacher@example.com"
$env:DEMO_ACCOUNT_PASSWORD = "<团队现场保管的强密码>"
$env:DEMO_CAPTURE_DIR = (Resolve-Path competition_submission/offline_backup).Path + "\video-capture-final"
node competition_submission/scripts/capture_demo_segments.mjs
```

脚本在同一浏览器页完成登录，记录登录结束时刻，再用FFmpeg重编码删除登录区间；原始含凭据视频立即删除，不保存Token文件。若Playwright本机尚无视频编码组件，可先执行`npx playwright install ffmpeg`，或由管理员把本机FFmpeg配置到Playwright缓存。

合成无声H.264预演并生成公开审计：

```powershell
py competition_submission/scripts/assemble_demo_preview.py `
  --segments competition_submission/offline_backup/video-capture-final `
  --output competition_submission/offline_backup/video-capture-final/星火智学_无声真实交互预演.mp4 `
  --public-audit competition_submission/03-Demo/VIDEO_SEGMENTS_AUDIT.json `
  --sampled-frames-reviewed
```

当前已验收版本为5段、总时长65.24秒、1600×900/25fps、浏览器错误0；65.2秒预演SHA见公开审计。原视频不入Git。最终成片还需按170秒脚本加入旁白/字幕、PR对抗快照与团队片尾，且总长不得超过180秒。

生成AI配音审片DRAFT：

```powershell
py competition_submission/scripts/build_narrated_demo.py `
  --segments competition_submission/offline_backup/video-capture-final `
  --output-dir competition_submission/offline_backup/narrated-video-final `
  --public-audit competition_submission/03-Demo/NARRATED_VIDEO_DRAFT_AUDIT.json
```

脚本使用本机`Microsoft Huihui Desktop`，把Guizang封面/案件架构/片尾、5段真实交互与2张去标识INV/PR审计快照组合，生成1080p H.264/AAC、中文字幕和全程AI配音标识。当前提议审片版121.6秒、约9.09MiB，10段旁白最大语速1.037倍，未检出超过1.2秒静音；视频SHA与七项内容覆盖见公开审计。它仍是DRAFT，不自动升级为最终参赛视频。
