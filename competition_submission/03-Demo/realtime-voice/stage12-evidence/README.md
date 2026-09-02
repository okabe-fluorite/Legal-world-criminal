# 阶段12：行末证据引用与实时语音证据

本目录保存可公开复核的脱敏截图、报告和讯飞 TTS 试听文件。截图来自本地真实浏览器验收；浏览器使用 Chromium 的真实媒体设备通道按实时钟播放确定性 PCM fixture，证明实时音频协议和页面交互，不等同于真实课堂多说话人 ASR 准确率。

## 复核内容

- `01-case-evidence-drawer.png`：可信 RAG 案例引用的完整来源抽屉，面向用户只展示来源类型、效力层级、版本/时效、引用原文、使用提示和原始来源链接；内部ID与SHA不在界面显示。
- `02-voice-evidence-natural-tts.png`：实时语音回复中的法条行末引用及完整 Evidence 抽屉；页面显示讯飞 TTS 小露女声和 AI 形成性反馈边界。
- `report.json`：本轮机器验收结果，包含引用数量、ASR 状态、真实输入电平、PCM/partial/final、TTS 音色、文件上传和 LearningEvent 边界，以及错误计数。
- `x4_yezi.wav`：讯飞在线 TTS 真实生成的试听文件，16kHz WAV，180,942 bytes；SHA-256 为 `be4950d12f267f492df5731110a51f5367393b4312935467c906eaff5d5876cb`。

## 证据边界

- 正文引用只证明检索结果与完整来源可追溯，不自动证明法律蕴含；争议问题仍需教师/法学专家复核。
- ASR 结果保持 `needs_review`，不创建 LearningEvent、不进入正式评分、不更新长期画像。
- 数字人仍为 `not_connected`；当前完成的是浏览器实时麦克风 PCM → 讯飞 IAT partial/final → Evidence 形成性回复 → 讯飞 TTS 播放。
- 不保存学生原始麦克风音频，不包含 `.env`、API Key、JWT 或签名 URL。
