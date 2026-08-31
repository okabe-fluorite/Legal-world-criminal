# 讯飞ASR/TTS真实接通验证

- 状态：`passed`
- 代码commit：`3f0915132bad541b24cb23815066198f3e625e0e`
- 真实调用：TTS `1` 次，IAT `1` 次
- TTS音频：`competition_submission/03-Demo/iflytek-speech/iflytek-tts-verification.wav`，207892字节，SHA-256 `ad341c972c4945e8d9eda300a44493d6ddd12ed85f005cba750c03963da1e80c`
- 音频：16000Hz、1声道、16bit、6.495秒
- IAT转写：罪刑法定原则要求法无明文规定不为罪法无明文规定不处罚。
- 归一化相似度：`1.0`
- 法学词检查：`{"罪刑法定": true, "明文规定": true, "不为罪": true, "不处罚": true}`

## 边界

- 这是合成测试句的真实云端往返，不是课堂数据或学习效果。
- ASR结果保持`needs_review`，不自动生成LearningEvent或正式成绩。
- TTS必须保留AI合成标识；数字人继续后置并保持`not_connected`。
- 公开产物不含APPID、APIKey、APISecret或签名URL。
