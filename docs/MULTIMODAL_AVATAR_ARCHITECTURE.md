# 多模态、语音与数字人架构及API

## 当前真实状态

| 能力 | 优先级 | 当前状态 | 可运行证据 |
|---|---|---|---|
| 私有音频/图片上传 | P1 | `implemented` | JWT用户隔离、≤15MB、类型白名单、SHA-256、sandbox相对存储 |
| ASR短音频转写 | P1 | `implemented / available_after_real_call` | 讯飞IAT v2真实转写；结果固定`needs_review`；能力状态区分未配置/待验证/已连接 |
| 图像OCR/论证种子 | P1 | `interface_reserved / not_connected` | 视觉分析任务契约已冻结 |
| 服务端TTS | P1 | `implemented / available_after_real_call` | 讯飞在线TTS v2生成当前用户私有WAV/MP3和下载端点 |
| 实时语音问答 | P1 | `implemented / verified` | AudioWorklet→16kHz PCM→JWT WebSocket→讯飞IAT partial/final→Evidence短答→TTS自动播放；桌面两轮/窄屏一轮/视频段通过 |
| 浏览器本地朗读 | P1 fallback | `implemented_on_client` | `SpeechSynthesis`现场真实朗读；不生成下载资产 |
| 数字人渲染 | P2 | `external_provider_required / not_connected` | 异步任务、AI标识、肖像同意门禁已冻结 |
| WebRTC房间/打断式全双工语音 | Beta后 | `deferred` | 当前比赛版使用浏览器PCM→后端WebSocket的半双工多轮对话，不引入房间/TURN/媒体集群 |

接口存在不代表厂商能力已经连接。ASR/TTS适配器已实现，新进程先显示`configured_not_verified`（无凭据则为`not_configured`），IAT握手成功后ASR、TTS真实合成成功后TTS才显示`available`。数字人和视觉Provider继续`not_connected`。

## 推荐架构

```text
浏览器麦克风/图片/教学文本
        │
        ▼
JWT + 类型/大小/AI标识/肖像同意门禁
        │
        ├── 实时语音WebSocket ── 16kHz PCM ── 讯飞IAT partial/final ── Evidence短答 ── 讯飞TTS
        ├── 私有资产服务 ── SHA-256 ── 用户sandbox
        │
        └── Media Job Service ── SQLite幂等兼容任务
                  │
                  ▼
           Provider Registry
        ┌─────────┼────────────┐
        │         │            │
      讯飞      本地ASR       Azure Avatar
    ASR/TTS/人   可选fallback    替代Provider
        │         │            │
        └─────────┴────────────┘
                  │
                  ▼
 not_connected / queued / running / succeeded / failed / needs_review
                  │
                  ▼
       交互结果（默认不生成LearningEvent）
                  │
       规则校验或教师审核后才可晋级候选证据
```

P1比赛版已经使用独立鉴权WebSocket完成浏览器麦克风实时多轮对话；HTTP异步任务保留给文件兼容、状态和审计。若Beta阶段需要打断、双工、多人房间和弱网治理，再在Provider层外增加LiveKit/WebRTC；实时媒体层仍不得直接调用adaptive画像。

## 已冻结API

| 方法 | 路径 | 作用 | 无Provider行为 |
|---|---|---|---|
| GET | `/api/media/capabilities` | secret-free能力与Provider目录 | 返回真实状态 |
| WS | `/ws/realtime-voice` | 16kHz PCM实时语音多轮：IAT partial/final→Evidence→TTS | 无凭据返回脱敏错误；JWT只走子协议，不进URL |
| POST | `/api/multimodal/assets` | multipart私有音频/图片上传 | 上传仍可用 |
| GET | `/api/multimodal/assets/{asset_id}` | 当前用户资产元数据 | 跨用户404 |
| GET | `/api/multimodal/assets/{asset_id}/content` | 当前用户私有媒体下载 | 跨用户404 |
| POST | `/api/multimodal/transcriptions` | 执行短音频ASR任务 | 无凭据`not_connected`；成功`needs_review` |
| GET | `/api/multimodal/transcriptions/{job_id}` | 查询ASR任务 | 返回已有状态 |
| POST | `/api/multimodal/visual-analyses` | OCR/论证种子/材料摘要任务 | 持久化`not_connected` |
| GET | `/api/multimodal/visual-analyses/{job_id}` | 查询视觉任务 | 返回已有状态 |
| POST | `/api/speech/synthesis` | 执行TTS任务并生成私有资产 | 无凭据`not_connected`；成功`succeeded` |
| GET | `/api/speech/jobs/{job_id}` | 查询TTS任务 | 返回已有状态 |
| POST | `/api/avatar/renders` | 创建数字人任务 | 持久化`not_connected` |
| GET | `/api/avatar/renders/{job_id}` | 查询数字人任务 | 返回已有状态 |
| GET | `/api/media/jobs/{job_id}` | 通用任务查询 | 跨用户404 |

同一`job_id`和同一请求返回`duplicate`；同ID改请求返回409。写接口在返回前显式提交事务，避免“上传已返回、紧接着的转写查不到资产”的竞态。

## Provider选择

### 首选：讯飞

- 流式听写官方WebAPI使用WebSocket，短会话最长60秒，支持8k/16k、16bit单声道PCM/Speex，普通话/英文另支持MP3；适合语音快问快答。官方文档：[语音听写（流式版）](https://www.xfyun.cn/doc/asr/voicedictation/API.html)。
- 在线TTS使用`wss://tts-api.xfyun.cn/v2/tts`，需要`APPID/APIKey/APISecret`，单次文本小于8000字节；旧HTTP普通版不应作为新实现。官方文档：[在线语音合成](https://www.xfyun.cn/doc/tts/online_tts/API.html)。
- 国内超拟人数字人公开资料目前更偏Android SDK；全球实时云接口还要求授权`avatar_id`和`vcn`。官方资料：[超拟人数字人交互SDK](https://www.xfyun.cn/doc/spark/Virtual_interaction.html)、[Virtual Human realtime API](https://global.xfyun.cn/doc/vms/virtualhuman/API.html)。

推荐原因：契合赛事生态、中国网络路径更现实、ASR/TTS能力完整。风险：数字人授权和Web端形态需要单独确认，不能仅有通用星火Key就宣称可用。

### 本地ASR候选：faster-whisper

`faster-whisper`为MIT许可，可使用CPU/GPU量化，适合作为可选离线ASR；但模型文件、首次下载、中文法律热词和现场性能必须在目标电脑实测。官方仓库：[SYSTRAN/faster-whisper](https://github.com/SYSTRAN/faster-whisper)。当前只保留配置槽，不宣称模型已下载。

### 数字人替代：Azure Speech Avatar

Azure支持批量异步和实时Avatar，标准视频Avatar可输出1080p/25fps；需要Speech/Foundry资源、区域和密钥，并按活跃时长或输出时长计费。官方文档：[Avatar overview](https://learn.microsoft.com/en-us/azure/ai-services/speech-service/text-to-speech-avatar/what-is-text-to-speech-avatar)、[Realtime synthesis](https://learn.microsoft.com/en-us/azure/ai-services/speech-service/text-to-speech-avatar/real-time-synthesis-avatar)。适合作为替代Provider，不适合作为中国比赛现场唯一链路。

### 实时媒体层：LiveKit（后置）

LiveKit官方支持WebRTC、STT→LLM→TTS流水线、打断/轮次检测和Provider插件，并可自托管。官方文档：[Agents](https://docs.livekit.io/agents/)、[Realtime media and data](https://docs.livekit.io/frontends/build/media-data/)。当前纵向切片不需要引入房间、TURN、令牌和媒体服务；只有当“实时口语对话”成为验收项时再接入。

## 服务端配置槽

```dotenv
XFYUN_APP_ID=
XFYUN_API_KEY=
XFYUN_API_SECRET=
XFYUN_AVATAR_ID=
XFYUN_AVATAR_VCN=
AZURE_SPEECH_KEY=
AZURE_SPEECH_REGION=
SIMLAW_FASTER_WHISPER_MODEL=
```

本地启动器也兼容用户外部配置文件中的`APPID/APIKey/APISecret`，只在子进程环境映射为`XFYUN_*`，不复制进仓库。凭据存在仍不等于可用；真实成功调用后当前进程才晋级`available`。能力目录永远不返回密钥值。

## 真实接通证据（2026-08-31—2026-09-01）

- `competition_submission/03-Demo/iflytek-speech/iflytek-tts-verification.wav`：真实讯飞TTS生成，207,892字节，16kHz/单声道/16bit/6.495秒，SHA-256 `ad341c972c4945e8d9eda300a44493d6ddd12ed85f005cba750c03963da1e80c`。
- 真实IAT转写：`罪刑法定原则要求法无明文规定不为罪法无明文规定不处罚。`；归一化相似度1.0，4个法学关键词全部命中。
- `IFLYTEK_ASR_TTS_VERIFICATION.json`绑定真实TTS 1次、IAT 1次和Provider会话存在性；不含密钥值或签名URL。
- 产品API与1500×980浏览器又完成真实`TTS→私有下载→IAT`，ASR/TTS为`available`、数字人为`not_connected`、网络/console/私有字段错误0。
- 实时产品主链完成桌面两轮384个PCM分片/54个partial/2个final/2个Evidence回复/2段TTS，窄屏单轮192分片，视频段194分片/28 partial；三次验收文件上传请求均为0，LearningEvent均为0→0，四类浏览器错误0。确定性麦克风fixture按真实媒体时钟工作，但不等于多说话人课堂ASR准确率。
- 阶段12最终专项验收重新验证行末引用与实时语音：6个RAG引用标记、案例完整Evidence抽屉和原始来源URL、201个PCM分片、27个partial、1个final、1条Evidence回复、`x4_yezi`首选女声、真实输入电平/设备名、文件上传0、LearningEvent 0→0，console/page/HTTP/request错误全0。专用脱敏材料见`competition_submission/03-Demo/realtime-voice/stage12-evidence/`。
- `x4_yezi`试听WAV为180,942字节、16kHz，SHA-256 `be4950d12f267f492df5731110a51f5367393b4312935467c906eaff5d5876cb`；该结果证明讯飞真实调用成功，不是主观自然度评分。

## 行末 Evidence 引用

可信RAG、AI分层解惑和实时语音回复共享`EvidenceCitations.vue`组件。每个标记绑定当前EvidencePack中的唯一Evidence ID；悬停只显示截断摘要，点击在`body`层打开完整抽屉，展示来源类型、法源层级、条号、逐字quote、版本/时效、快照、内容SHA、风险标签和原始链接。引用审查只验证来源存在、范围和逐字片段，不自动证明法律蕴含；抽屉和回复均保留教师/专家复核提示。

## 数据与教学边界

- 原始媒体只保存在当前用户私有sandbox，数据库仅保存相对storage key；API不返回主机绝对路径。
- ASR、OCR、TTS和Avatar任务不创建LearningEvent，不更新LearnerProfile，不进入正式评分。
- 若未来需要把转写变成主观题答案，必须让学生确认文本；若需要作为长期画像证据，还需引用审查、Rubric或教师审核。
- 自定义数字人必须确认肖像/声音授权；所有合成音视频必须显著标识AI生成。
- 原始媒体、Provider输出和密钥不得提交Git；公开包继续执行路径、密钥和私密材料扫描。

## 分阶段实施

1. **当前提交版（已完成）。**浏览器实时麦克风多轮、讯飞IAT partial/final、Evidence短答、讯飞TTS自动播放、私有上传兼容、任务台账、可下载音频和本地朗读降级。
2. **数字人前阶段（当前）。**ASR结果继续由规则/教师复核，不引入课堂画像；保留凭据轮换、配额和断网失败降级测试。
3. **P2可选。**确认数字人产品形态、API授权、标准角色和费用后，只把审核通过文本交给Avatar Provider；现场保留2D静态角色+TTS降级。
4. **Beta后。**真实学生同意与课堂口语需求成立时，再评估LiveKit/WebRTC多人/打断式双工、长录音转写、数据保留期限和教师转写审核队列。
