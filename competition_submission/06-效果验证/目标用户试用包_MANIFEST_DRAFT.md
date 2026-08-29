# 两名目标用户试用材料包MANIFEST（DRAFT）

> 材料已生成，但尚无真实参与者。`U01/U02`只是预分配编号，不代表已经试用。私密同意书不得进入公开比赛附件或Git之外的公开共享渠道。

## 冻结身份

| 字段 | 值 |
|---|---|
| Git commit | `74037f7c89c9683a1897550e5e6e50d712b463cb` |
| 法源manifest SHA-256 | `78360315a0e3b29f1c34bceeb3ccfde7ee75aa8b16c56efe3a8f20701f0e76d7` |
| 构建脚本 | `competition_submission/scripts/build_target_user_trial_package.py` |
| 构建日期 | `2026-08-30` |
| 预分配编号 | `U01、U02` |
| 真实参与者数量 | `0` |
| 真实记录完成 | `false` |

## 私密同意书包

仅由负责人和证据管理员离线保管。使用前必须填写撤回联系方式和证据管理员。

| 文件 | SHA-256 |
|---|---|
| `private/U01_知情同意书_私密.pdf` | `2b650ddefd7928ef58f4c926ce161462e1e6f337422bfaf41c900293b4890ea7` |
| `private/U02_知情同意书_私密.pdf` | `9132339f6b4e311885b911a8ff4ee2513d61ceebf066731d8dc553c47f1bb13e` |

私密ZIP SHA-256：`ba010c869664942f242885af2fc1c345b61b7693ec5225e1f02c6eaf085a8c4a`

## 去标识试用记录包

可交给主持人与记录人使用，不含身份、签署、联系方式或授权选项。

| 文件 | SHA-256 |
|---|---|
| `public/统一试用主持脚本.pdf` | `c160dd02f972720c17da1dd2beb3ef685266d67099932e3f6c41c5e205ba597e` |
| `public/U01_去标识试用记录.pdf` | `592d6e472dad6db50be34c54ca15ff3d0d2c56366d391816b8bc53998f5f81c5` |
| `public/U02_去标识试用记录.pdf` | `5f7870e33e99610dde9a82846787d2611cdfbc6ef1a7a5a355d452ccb0e33934` |
| `public/U01_U02去标识汇总模板.pdf` | `56db04ba930fcb398f91160748768af2fcf366b46fd8e2d107d9f201a462c7c5` |

去标识ZIP SHA-256：`b3973b0bed41f9aef9e87d704b50abe14530144155678f57c50a978219b9ccac`

## 构建与使用门禁

- `BUILD_AUDIT.json` SHA-256：`c79ac15a2ae486bb45b0f4ba3e5efffa9f038ecbf39db49ed9f4cc0d86a69da0`。
- 6份PDF共11页，均经Poppler逐页渲染检查；同意书各1页，去标识记录各3页。
- 私密/公开ZIP条目隔离通过；公开PDF私密字段0命中；API Key、私有路径和回答哈希0命中。
- U01/U02必须使用同一commit、同一法源和统一T1-T4；每项最多一次不含答案的提示。
- 2人样本只报告有效`n`、中位数和范围，不做显著性检验，不外推诊断效度或学习效果。
- 只有收到两份真实同意书和两份完成的去标识记录后，才能将`real_participant_count`改为2、填写汇总并更新PPT第12页。
