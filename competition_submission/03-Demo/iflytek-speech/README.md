# 讯飞ASR/TTS真实接通证据

本目录只保存公开、去密钥的多模态验收材料。`APPID/APIKey/APISecret`仅从仓库外`.env.example`运行时读取，没有复制、打印或提交。

## 真实云端闭环

- 输入文本：罪刑法定原则要求法无明文规定不为罪，法无明文规定不处罚。
- 讯飞在线TTS真实生成`iflytek-tts-verification.wav`：207,892字节、16kHz、单声道、16bit、6.495秒。
- 讯飞IAT真实转写：罪刑法定原则要求法无明文规定不为罪法无明文规定不处罚。
- 归一化相似度：1.0；法学词“罪刑法定/明文规定/不为罪/不处罚”4/4命中。
- TTS和IAT均返回Provider会话标识；详细门禁见`../IFLYTEK_ASR_TTS_VERIFICATION.json`。

## 产品闭环

- `browser-06-iflytek-tts-asr.png`：产品页真实生成、播放WAV并转写，ASR/TTS均`available`，转写`needs_review`。
- `browser-07-avatar-boundary.png`：同页保留数字人`not_connected`，证明数字人未被冒充为已完成。
- `browser-report.json`：1500×980浏览器实跑，5个媒体能力、3个available能力，私有字段、console/page/HTTP/request错误均为0。

## SHA-256

| 文件 | SHA-256 |
|---|---|
| `iflytek-tts-verification.wav` | `ad341c972c4945e8d9eda300a44493d6ddd12ed85f005cba750c03963da1e80c` |
| `browser-06-iflytek-tts-asr.png` | `12c06f84ba003810057bca11ac7ffde007ab36f19617624956b575bbf53cf962` |
| `browser-07-avatar-boundary.png` | `fd93f3af5a6e9ba74d865b789f7407989b9e5f5ac235f42c847f4d19db2ca466` |
| `browser-report.json` | `07759aeb8ad29054fa402b9ab0e8a24a4b56b9a7597e47a9d779bbbed60334bb` |

## 边界

- 这是合成验收句的真实云端往返，不是课堂数据或学习效果。
- ASR结果固定`needs_review`，不自动形成LearningEvent、长期画像或正式成绩。
- TTS保留AI合成标识；数字人继续后置。
