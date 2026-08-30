# 轻量2D法学AI助教

## 已完成形态

本项目实现的是“轻量2D数字导师 + 浏览器本地朗读降级”，不是Live2D Cubism模型，也不是已接通的讯飞虚拟人。

- 4张原创透明WebP：闭嘴、半开嘴、张嘴、眨眼；统一768×960、真实alpha、总计约382KB。
- CSS呼吸、轻摆和随机眨眼；`prefers-reduced-motion`下关闭持续动画。
- 浏览器`SpeechSynthesis`朗读时按145ms切换嘴形；它不生成下载音频，也不冒充讯飞TTS。
- 固定标识“AI助教·形成性反馈 / 非教师结论 / 不形成正式成绩”。
- 只在三类场景出现：受治理分层解惑、错误Evidence警告、个性化路径解释。

## 资产与生成边界

角色为原创非真人形象，未使用真实教师、法官或检察官肖像；不穿法袍、不拿法槌、无机构标志。基础角色与三个身份保持变体使用内置图像生成/编辑能力生成，最终WebP由FFmpeg机械统一画布与格式，不改变角色语义内容。

完整资产哈希、状态和提示摘要见`frontend/src/assets/tutor/manifest.json`。项目提交包只保留四张最终WebP；生成中间件不作为产品资产。

## 讯飞websdk-python参考边界

本地参考SDK采用Apache-2.0。当前只吸收其安全接口分层，不复制真实`.env`、密钥或运行结果：

- ASR：`xfyunsdkspeech.IatClient / LfasrClient / RtasrClient`；
- TTS：`xfyunsdkspeech.TtsClient`；
- OCR：`xfyunsdkocr`；
- 鉴权与传输：core HMAC签名和HTTP客户端。

`backend/src/media/providers/iflytek.py`仅提供脱敏Provider目录；即使检测到环境变量，仍保持`not_connected`，直到Adapter实现、服务授权和集成测试全部通过。Face、音色克隆、星火Agent和完整虚拟人不进入当前主线。

## 数据与教学边界

- ASR/OCR/TTS/角色交互默认不创建LearningEvent、不更新长期画像、不形成正式评分。
- ASR/OCR文本要进入评分或画像，必须先经过规则门禁或教师复核。
- 合成语音与角色输出保持AI显著标识；自定义肖像还需单独同意。
- 当前动画和朗读只证明交互机制可用，不证明学习效果。

## 展示映射

- 视频：分层解惑约8秒，展示4层解释、AI标识、朗读嘴形；路径页约4秒，展示推荐解释。
- PPT：交互应用页作为增强证据；不要占用核心技术页，也不得标注“已完成Live2D/讯飞数字人”。
- 评分：创新应用与完成度；核心技术得分仍由数据治理、Evidence推理、LegalEduEval和Agent消融承担。

## 验证

- 1500×980：认知路径、可信RAG错误门禁、真实模型分层解惑三条浏览器路线通过。
- 780×900：认知路径与真实模型分层解惑通过。
- 浏览器路线均为私有字段0、console/page/HTTP/request错误0。
- 四张WebP均为768×960、`yuva420p`；前端生产构建成功加载全部状态。
