# 两名目标用户试用材料包MANIFEST（DRAFT）

> 材料已生成，但尚无真实参与者。`U01/U02`只是预分配编号，不代表已经试用。私密同意书不得进入公开比赛附件或Git之外的公开共享渠道。

## 冻结身份

| 字段 | 值 |
|---|---|
| Git commit | `db616bc42aedbd79325edd5f13b2a16875a9c5ae` |
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
| `private/U01_知情同意书_私密.pdf` | `b4203f8902ca2245aa7db56b76349522bec37c83fb991b5881da6f12bbfff06d` |
| `private/U02_知情同意书_私密.pdf` | `c21626e321b58da309fc0c2c61def709f234edb54e1f857219ecfdbff7482ef6` |

私密ZIP SHA-256：`69f65afbfa6cd078001e132a295994edb00657f18fec6404998ad6b87b409eaf`

## 去标识试用记录包

可交给主持人与记录人使用，不含身份、签署、联系方式或授权选项。

| 文件 | SHA-256 |
|---|---|
| `public/统一试用主持脚本.pdf` | `58269615cf40e5d6b68611a7310f0a0e49f3d9aae4d49360b520fccada097141` |
| `public/U01_去标识试用记录.pdf` | `d1fd3aaa141704e1ce12251debf7b0bf5d43347b750f3f9fa066a71144ae6972` |
| `public/U02_去标识试用记录.pdf` | `72d0c876da35a0ef323d54bb0c1712002ff5d26c474fce0760b068ef799b9c78` |
| `public/U01_U02去标识汇总模板.pdf` | `493936059a77b5c01dd56145e704d82cc3718e2e3d229c285c55b4dd2b7e4cc0` |

去标识ZIP SHA-256：`8675380401463a2743b2534ac3e8c3f23887f41545bf8122ebe31b16cca5e2ef`

## 构建与使用门禁

- `BUILD_AUDIT.json` SHA-256：`c79ac15a2ae486bb45b0f4ba3e5efffa9f038ecbf39db49ed9f4cc0d86a69da0`。
- 6份PDF共11页，均经Poppler逐页渲染检查；同意书各1页，去标识记录各3页。
- 页脚已按材料角色标为“目标用户试用材料”，不再沿用专家审核页脚。
- 私密/公开ZIP条目隔离通过；公开PDF私密字段0命中；API Key、私有路径和回答哈希0命中。
- U01/U02必须使用同一commit、同一法源和统一T1-T4；每项最多一次不含答案的提示。
- 2人样本只报告有效`n`、中位数和范围，不做显著性检验，不外推诊断效度或学习效果。
- 只有收到两份真实同意书和两份完成的去标识记录后，才能将`real_participant_count`改为2、填写汇总并更新PPT第12页。
