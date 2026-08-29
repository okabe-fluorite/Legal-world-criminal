# 伦理与安全签署材料包MANIFEST（DRAFT）

> 公开声明、核对清单和私密签署页已生成，但尚无任何真实签名。团队责任声明不等于机构伦理委员会审批、学校授权、课堂试点批准或外部专家背书。

## 冻结身份

| 字段 | 值 |
|---|---|
| Git commit | `db616bc42aedbd79325edd5f13b2a16875a9c5ae` |
| 法源manifest SHA-256 | `78360315a0e3b29f1c34bceeb3ccfde7ee75aa8b16c56efe3a8f20701f0e76d7` |
| 构建脚本 | `competition_submission/scripts/build_ethics_signature_package.py` |
| 构建日期 | `2026-08-30` |
| 必需签署角色 | 团队负责人、指导教师、数据/安全责任人 |
| 真实签名数量 | `0/3` |
| 签署完成 | `false` |
| 机构伦理审批声明 | `false` |

## 公开声明包

| 文件 | 内容 | SHA-256 |
|---|---|---|
| `public/伦理与安全合规声明正文.pdf` | 用途、数据、AI、诊断、Agent、隐私、风险与发布边界 | `01e7064f62f1cb332e15f91a7e8e84d681735853f0a6803064794e7577e4b5e0` |
| `public/签署前核对清单.pdf` | 内容、隐私、法源、模型、外部证据和批准门禁 | `30e6bfd9e539f780ca9f381d65beed530f7da6611281928da6bc3e06196af4e8` |

公开ZIP SHA-256：`7975fb9763ee1cb08b4a4c608c2036432fb539b813261cdb73d395b6b3f0a8c3`

## 私密签署页包

| 文件 | 内容 | SHA-256 |
|---|---|---|
| `private/伦理声明签署页_私密.pdf` | 三名责任角色的姓名、签名、日期和公开授权选择 | `4ff4e14a6489c726fc0d41fca34dd76e6c04f2b973faaae3dd50faa0e6cbf826` |

私密ZIP SHA-256：`813cf2d9599c1d912d862a82b23c07fe1e53849bd151fb2d775b43ec1a3317c1`

## 构建与签署门禁

- `BUILD_AUDIT.json` SHA-256：`213b75260c80899f5cb69a717a2de9bf1c68a74937dbbd533ce55fffd8805ee6`。
- 3份PDF共7页，均经Poppler逐页渲染和视觉复核；公开/私密ZIP隔离通过。
- 公开PDF私密签署字段0命中；API Key、私有路径和回答哈希0命中。
- 三套PDF已使用正确材料页脚：专家审核、目标用户试用、伦理与安全签署互不混淆。
- 签署前必须逐项完成核对清单；未通过项先整改、更新commit和SHA，再签署。
- 签署后的私密页不得覆盖仓库空白模板或提交Git；仅离线保存其SHA和必要的公开授权结果。
- 即使三人签署完成，专家、目标用户和视频仍按各自证据状态独立判断，不自动从`PENDING/DRAFT`变为通过。
