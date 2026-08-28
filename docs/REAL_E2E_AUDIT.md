# 真实六阶段E2E审计

## 结论

2026-08-27完成`case_1`真实服务链路：前台 → LC → INV → PR → DS → CR → CRA → 结案。运行时优先请求OpenCode的`deepseek-v4-flash`；OpenCode工作区触发5小时窗口429后，统一Model Adapter自动切换DeepSeek官方`deepseek-v4-flash-vision-exp`，后续Agent通过共享熔断直接使用fallback。

本结果证明工程链路真实可运行，不证明学习增益、评分效度或法律结论质量。

该次E2E只运行`case_1`，其runtime ID与原案ID均为1。后续CaseBundle审计发现seed排序下`case_2→原案3`、`case_3→原案2`，并已修复教学参考映射；因此本报告不能替代case_2/3在新bundle版本上的真实E2E重跑。

## 可复核结果

- 总耗时：339.282秒；
- 学生测试回答：31次，均为固定独立回答，`assist_mode=none`；
- 对话继续门：70次；
- 到达阶段：LC、INV、PR、DS、CR、CRA；
- runtime issue：0；
- 结案：是；
- LearningEvent：6条，六阶段齐全；
- 长期画像资格：6/6 eligible；
- adaptive投递：6/6 sent；
- learner profile：存在，`event_count=6`；
- 版本化推荐记录：6条。

脱敏运行摘要保存在本机`D:\Legalworld_real_e2e_stage17_fallback_v2.json`，不含API Key、JWT或学生原始隐私数据。

## 运行中发现并修复

1. OpenCode限流后原逻辑只失败：新增瞬态错误自动fallback、共享熔断和脱敏catalog；401/400不回退。
2. DS测试回答不符合文书协议：E2E脚本改为首行“辩护词”、完整正文、末行`【起草结束】`并加抽取测试。
3. PR后台裁判三次偶发空响应：人工补评成功；随后增加阶段级30秒/120秒自动重试，已有事件或无学生证据时不重试。
4. PDF最初写入容器全局工作目录：改为所有DS/CR/CRA Agent显式接收每用户`case_output_dir`，并由本地测试验证三类PDF只能写入案件目录。
5. JWT曾位于WebSocket URL：改用`Sec-WebSocket-Protocol`，本地Vite与Nginx链路均验证成功，URL不含token。

## 证据边界

- 固定测试回答不是课堂真实学生数据；
- LLM评分属于形成性反馈，不得直接作为正式成绩；
- 当前掌握状态不是校准后的ORCDF概率；
- 3个发布案例仍要求法学教师每学期复核；
- 元典Key和大型案例向量索引未配置时，系统会明确显示对应工具失败/降级，但本地813条法条检索仍可用。
