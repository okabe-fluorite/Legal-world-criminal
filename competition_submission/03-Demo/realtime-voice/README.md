# 讯飞实时语音对话验收包

本目录证明的不是“上传一个音频文件再转写”，而是浏览器实时媒体链：

```text
浏览器MediaStream麦克风
→ AudioWorklet持续采集
→ 16kHz/16bit/单声道PCM、40ms分片
→ JWT鉴权WebSocket
→ 讯飞IAT partial/final
→ 受治理Evidence与形成性法学短答
→ 讯飞TTS WAV回传和浏览器自动播放
→ 下一轮语音
```

## 可复核文件

- `desktop-two-rounds.png`：1500×980，两轮完成时的页面状态。
- `narrow-one-round.png`：780×900窄屏状态。
- `reply-01.wav`、`reply-02.wav`：浏览器实际收到的两轮讯飞AI合成回复，不是学生麦克风原始录音。
- `report.json`：帧类型计数、TTS媒体属性、SHA-256、LearningEvent隔离和错误计数。

## 复现

启动本地栈后，在`frontend`目录运行：

```powershell
npm run smoke:voice
```

验收脚本用Chromium实时媒体设备按真实时钟播放法学WAV，后端收到的是`voice_audio` PCM分片，不调用文件上传API。这样可稳定复现浏览器麦克风协议和多轮交互，但不能据此宣称多说话人课堂ASR准确率。

## 证据边界

- ASR文本始终`needs_review`。
- 实时语音前后LearningEvent均为0，不形成正式成绩，不自动更新长期画像。
- Evidence检索相关性不是法律蕴含结论，争议问题仍需教师复核。
- 两段WAV均为AI合成语音并保留AI标识。
- 数字人仍为`not_connected`，继续后置。
