"""Build blinded A/B legal-expert review PDF packages for the three demo questions.

Stage A contains only the question, model output and governed sources. It must be
sent and locked before Stage B is disclosed. Stage B contains the draft standard
answers and deterministic automatic-gate report. No expert conclusion is created
by this script.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import zipfile
from datetime import date
from pathlib import Path
from typing import Any, Iterable
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas
from reportlab.platypus import (
    CondPageBreak,
    KeepTogether,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)
from pypdf import PdfReader


REPO = Path(__file__).resolve().parents[2]
SUBMISSION = REPO / "competition_submission"
EFFECT_DIR = SUBMISSION / "06-效果验证"
TYPICAL_REPORT = REPO / "docs" / "TYPICAL_QUESTION_EVALUATION.json"
LAW_MANIFEST = REPO / "backend" / "legal_corpus" / "processed" / "law_corpus_manifest.json"
DEFAULT_OUTPUT = EFFECT_DIR / "专家审核包_DRAFT"

FONT_REGULAR = Path(r"C:\Windows\Fonts\msyh.ttc")
FONT_BOLD = Path(r"C:\Windows\Fonts\msyhbd.ttc")
ACCENT = colors.HexColor("#002FA7")
INK = colors.HexColor("#171717")
GREY = colors.HexColor("#666666")
LIGHT = colors.HexColor("#F3F4F6")
LINE = colors.HexColor("#D8DADF")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def git_output(*args: str) -> str:
    return subprocess.check_output(["git", *args], cwd=REPO, text=True).strip()


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def split_token(value: str, width: int = 16) -> str:
    return " ".join(value[index : index + width] for index in range(0, len(value), width))


def html(value: Any) -> str:
    return escape(str(value or "")).replace("\n", "<br/>")


def register_fonts() -> None:
    for path in (FONT_REGULAR, FONT_BOLD):
        if not path.is_file():
            raise SystemExit(f"Required Chinese font not found: {path}")
    pdfmetrics.registerFont(TTFont("MSYH", str(FONT_REGULAR), subfontIndex=0))
    pdfmetrics.registerFont(TTFont("MSYH-Bold", str(FONT_BOLD), subfontIndex=0))


def styles() -> dict[str, ParagraphStyle]:
    sample = getSampleStyleSheet()
    return {
        "title": ParagraphStyle(
            "TitleZh",
            parent=sample["Title"],
            fontName="MSYH-Bold",
            fontSize=22,
            leading=29,
            textColor=INK,
            alignment=TA_LEFT,
            spaceAfter=8 * mm,
            wordWrap="CJK",
        ),
        "subtitle": ParagraphStyle(
            "SubtitleZh",
            parent=sample["Normal"],
            fontName="MSYH",
            fontSize=9,
            leading=14,
            textColor=GREY,
            spaceAfter=5 * mm,
            wordWrap="CJK",
        ),
        "h1": ParagraphStyle(
            "H1Zh",
            parent=sample["Heading1"],
            fontName="MSYH-Bold",
            fontSize=15,
            leading=21,
            textColor=INK,
            spaceBefore=3 * mm,
            spaceAfter=3 * mm,
            wordWrap="CJK",
        ),
        "h2": ParagraphStyle(
            "H2Zh",
            parent=sample["Heading2"],
            fontName="MSYH-Bold",
            fontSize=11,
            leading=16,
            textColor=ACCENT,
            spaceBefore=3 * mm,
            spaceAfter=2 * mm,
            wordWrap="CJK",
        ),
        "body": ParagraphStyle(
            "BodyZh",
            parent=sample["BodyText"],
            fontName="MSYH",
            fontSize=9.2,
            leading=15,
            textColor=INK,
            spaceAfter=2.5 * mm,
            wordWrap="CJK",
        ),
        "small": ParagraphStyle(
            "SmallZh",
            parent=sample["BodyText"],
            fontName="MSYH",
            fontSize=7.3,
            leading=11,
            textColor=GREY,
            spaceAfter=1.5 * mm,
            wordWrap="CJK",
        ),
        "cell": ParagraphStyle(
            "CellZh",
            parent=sample["BodyText"],
            fontName="MSYH",
            fontSize=7.6,
            leading=11.5,
            textColor=INK,
            wordWrap="CJK",
        ),
        "cell_bold": ParagraphStyle(
            "CellBoldZh",
            parent=sample["BodyText"],
            fontName="MSYH-Bold",
            fontSize=7.6,
            leading=11.5,
            textColor=INK,
            wordWrap="CJK",
        ),
        "center": ParagraphStyle(
            "CenterZh",
            parent=sample["BodyText"],
            fontName="MSYH",
            fontSize=8,
            leading=12,
            alignment=TA_CENTER,
            wordWrap="CJK",
        ),
    }


class InvariantCanvas(canvas.Canvas):
    def __init__(self, *args: Any, **kwargs: Any) -> None:
        kwargs["invariant"] = 1
        super().__init__(*args, **kwargs)


def page_footer(pdf: canvas.Canvas, doc: SimpleDocTemplate) -> None:
    pdf.saveState()
    pdf.setStrokeColor(LINE)
    pdf.setLineWidth(0.4)
    pdf.line(18 * mm, 13 * mm, A4[0] - 18 * mm, 13 * mm)
    pdf.setFont("MSYH", 7)
    pdf.setFillColor(GREY)
    footer_label = getattr(doc, "footer_label", "星火智学 · XH-202620 · 独立法学专家审核材料")
    pdf.drawString(18 * mm, 8.5 * mm, footer_label)
    pdf.drawRightString(A4[0] - 18 * mm, 8.5 * mm, f"{doc.page}")
    pdf.restoreState()


def build_pdf(
    path: Path,
    title: str,
    story: list[Any],
    footer_label: str = "星火智学 · XH-202620 · 独立法学专家审核材料",
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    doc = SimpleDocTemplate(
        str(path),
        pagesize=A4,
        title=title,
        author="星火智学团队",
        subject="XH-202620独立法学专家审核材料",
        leftMargin=18 * mm,
        rightMargin=18 * mm,
        topMargin=17 * mm,
        bottomMargin=19 * mm,
    )
    doc.footer_label = footer_label
    doc.build(story, onFirstPage=page_footer, onLaterPages=page_footer, canvasmaker=InvariantCanvas)


def p(text: Any, style: ParagraphStyle) -> Paragraph:
    return Paragraph(html(text), style)


def label_value_table(rows: Iterable[tuple[str, Any]], st: dict[str, ParagraphStyle]) -> Table:
    data = [[p(label, st["cell_bold"]), p(value, st["cell"])] for label, value in rows]
    table = Table(data, colWidths=[39 * mm, 132 * mm], repeatRows=0)
    table.setStyle(
        TableStyle(
            [
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("BACKGROUND", (0, 0), (0, -1), LIGHT),
                ("GRID", (0, 0), (-1, -1), 0.35, LINE),
                ("LEFTPADDING", (0, 0), (-1, -1), 5),
                ("RIGHTPADDING", (0, 0), (-1, -1), 5),
                ("TOPPADDING", (0, 0), (-1, -1), 5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            ]
        )
    )
    return table


def section_header(text: str, st: dict[str, ParagraphStyle]) -> list[Any]:
    return [Spacer(1, 1.5 * mm), p(text, st["h2"])]


def bullet_rows(items: Iterable[str], st: dict[str, ParagraphStyle]) -> list[Any]:
    return [p(f"- {item}", st["body"]) for item in items]


def case_a_story(case: dict[str, Any], metadata: dict[str, Any], st: dict[str, ParagraphStyle]) -> list[Any]:
    output = case["model_output"]
    story: list[Any] = [
        p("A阶段独立判断材料", st["title"]),
        p(
            "本材料仅包含问题、系统输出和审核时可见来源。未包含标准答案草案、必需得分点、自动门禁结果或任何专家结论。请先独立判断并锁定A阶段审核表。",
            st["subtitle"],
        ),
        label_value_table(
            [
                ("题号", case["case_id"]),
                ("题目", case["title"]),
                ("模型", metadata["model_name"]),
                ("Provider", metadata["provider"]),
                ("任务路由", metadata["task"]),
                ("运行时间", metadata["generated_at"]),
                ("Suite SHA-256", split_token(metadata["suite_sha256"])),
                ("法源manifest SHA-256", split_token(metadata["law_manifest_sha256"])),
            ],
            st,
        ),
        Spacer(1, 5 * mm),
        p("一、问题", st["h1"]),
        p(case["question"], st["body"]),
        p("二、系统输出", st["h1"]),
        p("回答", st["h2"]),
        p(output.get("answer"), st["body"]),
        p("推理步骤", st["h2"]),
        *bullet_rows(output.get("rule_steps") or [], st),
        p("结论", st["h2"]),
        p(output.get("conclusion"), st["body"]),
        p("不确定性/限定语", st["h2"]),
        p(output.get("uncertainty") or "未提供", st["body"]),
        p("系统引用", st["h2"]),
    ]
    for index, citation in enumerate(output.get("citations") or [], start=1):
        story.extend(
            [
                KeepTogether(
                    [
                        p(
                            f"{index}. {citation.get('title', '')} {citation.get('article_ref', '')}",
                            st["cell_bold"],
                        ),
                        p(citation.get("quote"), st["small"]),
                    ]
                ),
                Spacer(1, 1.5 * mm),
            ]
        )
    story.extend([CondPageBreak(55 * mm), p("三、审核时可见来源", st["h1"])])
    for index, source in enumerate(case.get("sources") or [], start=1):
        rows = [
            ("来源", f"{source.get('title', '')} {source.get('article_ref', '')}"),
            ("类型/权威", f"{source.get('source_type', '')} / {source.get('authority', '')}"),
            ("版本", source.get("version", "")),
            ("来源URL", source.get("source_url") or "本地受治理课程材料"),
        ]
        bundle_sha = source.get("source_bundle_sha256") or source.get("local_source_sha256")
        if bundle_sha:
            rows.append(("来源SHA-256", split_token(bundle_sha)))
        story.extend(
            [
                p(f"来源 {index:02d}", st["h2"]),
                label_value_table(rows, st),
                Spacer(1, 2 * mm),
                p("审核原文", st["cell_bold"]),
                p(source.get("quote"), st["body"]),
                Spacer(1, 3 * mm),
            ]
        )
    story.extend(
        [
            p("A阶段审核提醒", st["h1"]),
            p(
                "请评价法律结论、规则完整性、来源有效性、事实-规则涵摄、争议边界与误导风险。不要打开B阶段压缩包；完成后签名并记录A阶段表文件SHA-256。",
                st["body"],
            ),
        ]
    )
    return story


def a_review_form_story(cases: list[dict[str, Any]], st: dict[str, ParagraphStyle]) -> list[Any]:
    story: list[Any] = [
        p("独立法学专家审核表 · A阶段盲判", st["title"]),
        p(
            "A阶段只查看问题、系统输出和权威来源。不得查看标准答案草案、自动门禁总分或B阶段材料。请用本人专业判断完成每题，并在末页锁定签名。",
            st["subtitle"],
        ),
        label_value_table(
            [
                ("A阶段压缩包SHA-256", "[从A阶段_独立判断包_DRAFT.zip.sha256.txt抄录]"),
                ("审核人编号", "[填写]"),
                ("专业背景/职称", "[填写]"),
                ("审核日期", "[YYYY-MM-DD]"),
            ],
            st,
        ),
        PageBreak(),
    ]
    dimensions = [
        ("法律结论", "正确 / 部分正确 / 错误 / 无法判断"),
        ("规则与要件完整性", "充分 / 基本充分 / 缺失"),
        ("法条/案例来源有效性", "通过 / 需更新 / 不通过"),
        ("事实-规则涵摄", "充分 / 基本充分 / 缺失"),
        ("争议边界与限定语", "充分 / 基本充分 / 缺失"),
        ("误导风险", "无 / 低 / 中 / 高"),
        ("A阶段建议", "可发布 / 修改后发布 / 拒绝发布"),
    ]
    for index, case in enumerate(cases):
        story.extend(
            [
                p(f"题目 {index + 1:02d} · {case['title']}", st["h1"]),
                p(case["case_id"], st["small"]),
                p(case["question"], st["small"]),
            ]
        )
        data = [[p("维度", st["cell_bold"]), p("A阶段结论", st["cell_bold"]), p("具体意见", st["cell_bold"])]]
        for label, choices in dimensions:
            data.append([p(label, st["cell"]), p(choices, st["cell"]), p("\n\n", st["cell"])])
        table = Table(data, colWidths=[36 * mm, 58 * mm, 77 * mm], repeatRows=1, rowHeights=[9 * mm] + [17 * mm] * len(dimensions))
        table.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), LIGHT),
                    ("GRID", (0, 0), (-1, -1), 0.35, LINE),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("LEFTPADDING", (0, 0), (-1, -1), 4),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 4),
                    ("TOPPADDING", (0, 0), (-1, -1), 4),
                ]
            )
        )
        story.extend(
            [
                table,
                Spacer(1, 3 * mm),
                p("必要修改（无则写“无”）：", st["cell_bold"]),
                p("\n\n\n", st["body"]),
            ]
        )
        if index < len(cases) - 1:
            story.append(PageBreak())
    story.extend(
        [
            PageBreak(),
            p("A阶段锁定", st["title"]),
            p("我确认以上意见在看到标准答案草案和自动门禁前独立完成；锁定后不改写A阶段意见。", st["body"]),
            Spacer(1, 12 * mm),
            label_value_table(
                [
                    ("审核人签名", "[本人签名]"),
                    ("锁定时间", "[YYYY-MM-DD HH:mm]"),
                    ("签名后A阶段表SHA-256", "[填写]"),
                ],
                st,
            ),
        ]
    )
    return story


def standard_answers_story(cases: list[dict[str, Any]], st: dict[str, ParagraphStyle]) -> list[Any]:
    story: list[Any] = [
        p("B阶段材料 · 三题标准答案草案", st["title"]),
        p("仅在A阶段审核表锁定后提供。本文件仍是课程与比赛用标准答案草案，不替代独立专家结论。", st["subtitle"]),
    ]
    for index, case in enumerate(cases):
        story.extend(
            [
                p(f"题目 {index + 1:02d} · {case['title']}", st["h1"]),
                p(case["case_id"], st["small"]),
                p("问题", st["h2"]),
                p(case["question"], st["body"]),
                p("标准答案草案", st["h2"]),
                p(case["standard_answer"], st["body"]),
                p("制定依据", st["h2"]),
                *bullet_rows(
                    [
                        f"必需来源ID：{', '.join(case.get('required_source_ids') or [])}",
                        *[f"{row['point_id']}：{row['label']}" for row in case.get("required_points") or []],
                    ],
                    st,
                ),
            ]
        )
        if index < len(cases) - 1:
            story.append(PageBreak())
    return story


def automatic_gate_story(report: dict[str, Any], st: dict[str, ParagraphStyle]) -> list[Any]:
    cases = report["cases"]
    story: list[Any] = [
        p("B阶段材料 · 自动门禁报告", st["title"]),
        p(
            "自动门禁只检查JSON结构、标准要点覆盖、允许来源和逐字quote。3/3通过不等于专家准确率，也不替代事实涵摄与争议判断。",
            st["subtitle"],
        ),
        label_value_table(
            [
                ("报告生成时间", report["generated_at"]),
                ("运行模式", report.get("mode")),
                ("题目数", report.get("case_count")),
                ("自动门禁通过", f"{report.get('automated_gate_pass_count')}/{report.get('case_count')}"),
                ("专家审核全部完成", "否" if not report.get("all_expert_reviews_complete") else "是"),
                ("Suite SHA-256", split_token(report["suite_sha256"])),
                ("法源manifest SHA-256", split_token(report["law_manifest_sha256"])),
            ],
            st,
        ),
        Spacer(1, 4 * mm),
    ]
    for index, case in enumerate(cases):
        point_rows = [
            [p("要点", st["cell_bold"]), p("结果", st["cell_bold"]), p("命中词", st["cell_bold"])]
        ]
        for point in case.get("point_audit") or []:
            point_rows.append(
                [
                    p(f"{point.get('label')} ({point.get('point_id')})", st["cell"]),
                    p("通过" if point.get("passed") else "未通过", st["cell"]),
                    p("、".join(point.get("matched_keywords") or []) or "无", st["cell"]),
                ]
            )
        table = Table(point_rows, colWidths=[86 * mm, 25 * mm, 60 * mm], repeatRows=1)
        table.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), LIGHT),
                    ("GRID", (0, 0), (-1, -1), 0.35, LINE),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("LEFTPADDING", (0, 0), (-1, -1), 4),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 4),
                    ("TOPPADDING", (0, 0), (-1, -1), 4),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                ]
            )
        )
        story.extend(
            [
                p(f"题目 {index + 1:02d} · {case['title']}", st["h1"]),
                p(case["case_id"], st["small"]),
                label_value_table(
                    [
                        ("结构门禁", "通过" if case.get("structural_pass") else "未通过"),
                        ("要点覆盖", f"{case.get('point_coverage', 0):.2f}"),
                        ("引用门禁", "通过" if case.get("citation_audit", {}).get("passed") else "未通过"),
                        ("自动总门禁", "通过" if case.get("automated_gate_pass") else "未通过"),
                        ("专家状态", case.get("expert_review_status")),
                        ("已验证准确", "否" if not case.get("verified_accurate") else "是"),
                    ],
                    st,
                ),
                Spacer(1, 3 * mm),
                table,
            ]
        )
        if index < len(cases) - 1:
            story.append(PageBreak())
    return story


def b_review_form_story(st: dict[str, ParagraphStyle]) -> list[Any]:
    data = [
        [p("题目", st["cell_bold"]), p("A阶段结论", st["cell_bold"]), p("与标准草案差异", st["cell_bold"]), p("自动门禁遗漏/误判", st["cell_bold"]), p("最终处置", st["cell_bold"])],
    ]
    for case_id in ("TQ01", "TQ02", "TQ03"):
        data.append([p(case_id, st["cell"]), p("[只读抄录]", st["cell"]), p("\n\n", st["cell"]), p("\n\n", st["cell"]), p("可发布 / 修改后发布 / 拒绝", st["cell"])])
    table = Table(data, colWidths=[16 * mm, 31 * mm, 42 * mm, 42 * mm, 40 * mm], repeatRows=1, rowHeights=[12 * mm, 29 * mm, 29 * mm, 29 * mm])
    table.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, 0), LIGHT), ("GRID", (0, 0), (-1, -1), 0.35, LINE), ("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (-1, -1), 3), ("RIGHTPADDING", (0, 0), (-1, -1), 3), ("TOPPADDING", (0, 0), (-1, -1), 4)]))
    return [
        p("独立法学专家差异复核表 · B阶段", st["title"]),
        p("仅在A阶段锁定后使用。不得改写A阶段意见；本表记录与标准答案草案及自动门禁的差异。", st["subtitle"]),
        label_value_table(
            [
                ("B阶段压缩包SHA-256", "[从B阶段_差异核对包_DRAFT.zip.sha256.txt抄录]"),
                ("A阶段表SHA-256", "[填写]"),
                ("审核人编号", "[填写]"),
            ],
            st,
        ),
        Spacer(1, 4 * mm),
        table,
        Spacer(1, 5 * mm),
        p("主要共性风险：", st["cell_bold"]),
        p("\n\n", st["body"]),
        p("课堂使用限制建议：", st["cell_bold"]),
        p("\n\n", st["body"]),
        label_value_table(
            [
                ("比赛材料引用授权", "实名 / 仅审核人编号 / 不引用"),
                ("审核人签名", "[本人签名]"),
                ("B阶段完成时间", "[YYYY-MM-DD HH:mm]"),
                ("签名后B阶段表SHA-256", "[填写]"),
            ],
            st,
        ),
    ]


def revision_form_story(st: dict[str, ParagraphStyle]) -> list[Any]:
    data = [[p(label, st["cell_bold"]) for label in ("题目", "old run/SHA", "专家整改要求", "修改人/日期", "new run/SHA", "门禁重跑", "复核结论", "复签人/日期")]]
    for _ in range(3):
        data.append([p("", st["cell"]) for _ in range(8)])
    table = Table(data, colWidths=[14 * mm, 22 * mm, 34 * mm, 22 * mm, 22 * mm, 22 * mm, 22 * mm, 21 * mm], repeatRows=1, rowHeights=[12 * mm, 30 * mm, 30 * mm, 30 * mm])
    table.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, 0), LIGHT), ("GRID", (0, 0), (-1, -1), 0.35, LINE), ("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (-1, -1), 2), ("RIGHTPADDING", (0, 0), (-1, -1), 2), ("TOPPADDING", (0, 0), (-1, -1), 3)]))
    return [
        p("专家整改与复签记录", st["title"]),
        p("仅在B阶段出现“修改后发布”或“拒绝发布”时使用。每次整改追加记录，不覆盖旧版本。", st["subtitle"]),
        table,
        Spacer(1, 6 * mm),
        label_value_table(
            [
                ("最终进入PPT/视频的run ID", "[填写]"),
                ("旧版本封存位置及manifest SHA", "[填写]"),
                ("最终复核人/日期", "[本人签名 / YYYY-MM-DD]"),
            ],
            st,
        ),
    ]


def safe_source_manifest(report: dict[str, Any], commit: str) -> dict[str, Any]:
    cases = []
    for case in report["cases"]:
        cases.append(
            {
                "case_id": case["case_id"],
                "title": case["title"],
                "run_status": case.get("run_status"),
                "model_route": {
                    key: case.get("model_route", {}).get(key)
                    for key in ("task", "provider", "model_name", "api_base")
                },
                "sources": [
                    {
                        key: source.get(key)
                        for key in (
                            "source_id",
                            "source_type",
                            "title",
                            "article_ref",
                            "authority",
                            "version",
                            "source_url",
                            "source_bundle_sha256",
                            "local_source_sha256",
                        )
                        if source.get(key) not in (None, "")
                    }
                    for source in case.get("sources") or []
                ],
            }
        )
    return {
        "schema": "expert-review-source-manifest-v1",
        "source_git_commit": commit,
        "evaluation_generated_at": report["generated_at"],
        "suite_sha256": report["suite_sha256"],
        "law_manifest_sha256": report["law_manifest_sha256"],
        "case_bundle_manifest_sha256": report.get("case_bundle_manifest_sha256"),
        "cases": cases,
        "security_boundary": "API keys, configured booleans, private paths and response hashes are excluded",
    }


def deterministic_zip(zip_path: Path, base: Path, files: list[Path]) -> None:
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for path in sorted(files, key=lambda value: value.as_posix()):
            info = zipfile.ZipInfo(path.relative_to(base).as_posix(), date_time=(2026, 8, 30, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o644 << 16
            archive.writestr(info, path.read_bytes())


def pdf_text(path: Path) -> str:
    return "\n".join(page.extract_text() or "" for page in PdfReader(str(path)).pages)


def verify_build(
    output: Path,
    a_files: list[Path],
    b_files: list[Path],
    revision_path: Path,
    a_manifest_path: Path,
    b_manifest_path: Path,
    a_zip: Path,
    b_zip: Path,
) -> dict[str, Any]:
    pdfs = [*a_files, *[path for path in b_files if path.suffix.lower() == ".pdf"], revision_path]
    pdf_pages: dict[str, int] = {}
    extracted: dict[str, str] = {}
    for path in pdfs:
        reader = PdfReader(str(path))
        if not reader.pages:
            raise SystemExit(f"Generated PDF has no pages: {path}")
        relative = path.relative_to(output).as_posix()
        pdf_pages[relative] = len(reader.pages)
        extracted[relative] = "\n".join(page.extract_text() or "" for page in reader.pages)

    with zipfile.ZipFile(a_zip) as archive:
        a_zip_names = sorted(archive.namelist())
    with zipfile.ZipFile(b_zip) as archive:
        b_zip_names = sorted(archive.namelist())
    a_expected = sorted(path.relative_to(output).as_posix() for path in [*a_files, a_manifest_path])
    b_expected = sorted(path.relative_to(output).as_posix() for path in [*b_files, b_manifest_path, revision_path])
    if a_zip_names != a_expected:
        raise SystemExit(f"Unexpected A-stage zip contents: {a_zip_names}")
    if b_zip_names != b_expected:
        raise SystemExit(f"Unexpected B-stage zip contents: {b_zip_names}")

    a_text = "\n".join(extracted[path.relative_to(output).as_posix()] for path in a_files)
    blinded_forbidden = [
        "自动门禁报告",
        "自动总门禁",
        "要点覆盖",
        "制定依据",
        "必需来源ID",
        "point_coverage",
        "automated_gate_pass",
    ]
    blinded_hits = [value for value in blinded_forbidden if value in a_text]
    if blinded_hits:
        raise SystemExit(f"A-stage blinding violation: {blinded_hits}")

    material_text = "\n".join(extracted.values())
    material_text += "\n" + (b_files[-2].read_text(encoding="utf-8") if b_files[-2].suffix == ".json" else "")
    secret_patterns = ["api_key_configured", "source_response_sha256", "PRIVATE KEY", "sk-", "D:\\Code\\"]
    secret_hits = [value for value in secret_patterns if value in material_text]
    if secret_hits:
        raise SystemExit(f"Sensitive material leaked into package: {secret_hits}")

    manifest_results: dict[str, bool] = {}
    for manifest_path in (a_manifest_path, b_manifest_path):
        payload = load_json(manifest_path)
        for row in payload["files"]:
            file_path = output / row["path"]
            key = f"{manifest_path.name}:{row['path']}"
            manifest_results[key] = (
                file_path.is_file()
                and file_path.stat().st_size == row["bytes"]
                and sha256(file_path) == row["sha256"]
            )
    if not manifest_results or not all(manifest_results.values()):
        raise SystemExit("Stage manifest hash verification failed")

    required_text = {
        "A/独立法学专家审核表_A阶段.pdf": ["A阶段锁定", "TQ01", "TQ02", "TQ03"],
        "B/standard_answers.pdf": ["标准答案草案", "TQ01", "TQ02", "TQ03"],
        "B/automatic_gate_report.pdf": ["自动门禁报告", "3/3", "专家审核全部完成"],
        "B/独立法学专家差异复核表_B阶段.pdf": ["A阶段表SHA-256", "不得改写A阶段意见"],
        "revision/专家整改复签记录.pdf": ["不覆盖旧版本", "最终进入PPT/视频的run ID"],
    }
    text_checks: dict[str, bool] = {}
    for relative, needles in required_text.items():
        text_checks[relative] = all(needle in extracted[relative] for needle in needles)
    if not all(text_checks.values()):
        raise SystemExit(f"Required PDF text missing: {text_checks}")

    return {
        "schema": "expert-review-package-build-audit-v1",
        "pdf_count": len(pdfs),
        "pdf_pages": pdf_pages,
        "a_stage": {
            "zip_entries": a_zip_names,
            "forbidden_blinding_hits": blinded_hits,
            "blinding_passed": True,
        },
        "b_stage": {"zip_entries": b_zip_names},
        "secret_scan": {"patterns": secret_patterns, "hits": secret_hits, "passed": True},
        "stage_manifest_checks": manifest_results,
        "required_text_checks": text_checks,
        "expert_review_complete": False,
        "evidence_boundary": "Build and QA only; no expert conclusion, signature or publication approval is created",
    }


def stage_manifest(stage: str, base: Path, files: list[Path], boundary: str) -> dict[str, Any]:
    return {
        "schema": "expert-review-stage-manifest-v1",
        "stage": stage,
        "files": [
            {
                "path": path.relative_to(base).as_posix(),
                "bytes": path.stat().st_size,
                "sha256": sha256(path),
            }
            for path in sorted(files, key=lambda value: value.as_posix())
        ],
        "boundary": boundary,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()

    register_fonts()
    st = styles()
    report = load_json(TYPICAL_REPORT)
    law_manifest = load_json(LAW_MANIFEST)
    output = args.output.resolve()
    a_dir = output / "A"
    b_dir = output / "B"
    revision_dir = output / "revision"
    for directory in (a_dir, b_dir, revision_dir):
        directory.mkdir(parents=True, exist_ok=True)

    commit = git_output("rev-parse", "HEAD")
    route = report["cases"][0]["model_route"]
    metadata = {
        "generated_at": report["generated_at"],
        "suite_sha256": report["suite_sha256"],
        "law_manifest_sha256": report["law_manifest_sha256"],
        "task": route["task"],
        "provider": route["provider"],
        "model_name": route["model_name"],
    }

    a_files: list[Path] = []
    for index, case in enumerate(report["cases"], start=1):
        path = a_dir / f"TQ{index:02d}_question_output_sources.pdf"
        build_pdf(path, f"A阶段 · {case['title']}", case_a_story(case, metadata, st))
        a_files.append(path)
    a_form = a_dir / "独立法学专家审核表_A阶段.pdf"
    build_pdf(a_form, "独立法学专家审核表 · A阶段", a_review_form_story(report["cases"], st))
    a_files.append(a_form)

    standard_path = b_dir / "standard_answers.pdf"
    gate_path = b_dir / "automatic_gate_report.pdf"
    b_form = b_dir / "独立法学专家差异复核表_B阶段.pdf"
    source_manifest_path = b_dir / "source_manifest.json"
    build_pdf(standard_path, "三题标准答案草案", standard_answers_story(report["cases"], st))
    build_pdf(gate_path, "三题自动门禁报告", automatic_gate_story(report, st))
    build_pdf(b_form, "独立法学专家差异复核表 · B阶段", b_review_form_story(st))
    write_json(source_manifest_path, safe_source_manifest(report, commit))
    b_files = [standard_path, gate_path, source_manifest_path, b_form]

    revision_path = revision_dir / "专家整改复签记录.pdf"
    build_pdf(revision_path, "专家整改与复签记录", revision_form_story(st))

    a_manifest_path = a_dir / "A_MANIFEST.json"
    write_json(
        a_manifest_path,
        stage_manifest(
            "A_blinded_independent_review",
            output,
            a_files,
            "No draft standard answer, required-point audit, automatic gate result or expert conclusion is included",
        ),
    )
    a_zip_inputs = [*a_files, a_manifest_path]
    a_zip = output / "A阶段_独立判断包_DRAFT.zip"
    deterministic_zip(a_zip, output, a_zip_inputs)

    b_manifest_path = b_dir / "B_MANIFEST.json"
    write_json(
        b_manifest_path,
        stage_manifest(
            "B_difference_review_after_A_lock",
            output,
            b_files,
            "Disclose only after the signed Stage A form is locked and hashed",
        ),
    )
    b_zip_inputs = [*b_files, b_manifest_path, revision_path]
    b_zip = output / "B阶段_差异核对包_DRAFT.zip"
    deterministic_zip(b_zip, output, b_zip_inputs)

    a_sha_path = output / f"{a_zip.name}.sha256.txt"
    b_sha_path = output / f"{b_zip.name}.sha256.txt"
    a_sha_path.write_text(f"{sha256(a_zip)}  {a_zip.name}\n", encoding="utf-8")
    b_sha_path.write_text(f"{sha256(b_zip)}  {b_zip.name}\n", encoding="utf-8")

    readme = f"""# 三题独立法学专家审核包（DRAFT）

构建来源：`{commit}`

模型路由：`{route['provider']} / {route['model_name']} / {route['task']}`
三题自动门禁：`{report['automated_gate_pass_count']}/{report['case_count']}`，但专家仍未完成。

## 使用顺序

1. 只发送`A阶段_独立判断包_DRAFT.zip`及同名SHA文件。
2. 专家独立完成并签署A阶段表；团队计算签名后PDF的SHA-256并锁定。
3. A阶段锁定后，才发送`B阶段_差异核对包_DRAFT.zip`及同名SHA文件。
4. 专家完成B阶段差异复核；如要求修改，使用`revision/专家整改复签记录.pdf`追加记录。

## 强制边界

- A包不含标准答案草案、必需得分点、自动门禁结果或专家结论。
- B包中的3/3只是自动门禁，不等于专家准确率。
- 本构建脚本不会生成专家签名、审核结论或发布许可。
- `MANIFEST.json`记录所有发布文件与压缩包SHA-256；API Key、私有路径和回答哈希均未纳入。
"""
    readme_path = output / "README.md"
    readme_path.write_text(readme, encoding="utf-8")

    build_audit_path = output / "BUILD_AUDIT.json"
    write_json(
        build_audit_path,
        verify_build(
            output,
            a_files,
            b_files,
            revision_path,
            a_manifest_path,
            b_manifest_path,
            a_zip,
            b_zip,
        ),
    )

    all_files = [
        *a_zip_inputs,
        *b_zip_inputs,
        a_zip,
        b_zip,
        a_sha_path,
        b_sha_path,
        readme_path,
        build_audit_path,
    ]
    root_manifest = {
        "schema": "expert-review-package-manifest-v1",
        "source_git_commit": commit,
        "package_build_date": date(2026, 8, 30).isoformat(),
        "evaluation_report": {
            "path": TYPICAL_REPORT.relative_to(REPO).as_posix(),
            "sha256": sha256(TYPICAL_REPORT),
            "generated_at": report["generated_at"],
            "case_count": report["case_count"],
            "automated_gate_pass_count": report["automated_gate_pass_count"],
            "all_expert_reviews_complete": report["all_expert_reviews_complete"],
        },
        "model_route": {
            "task": route["task"],
            "provider": route["provider"],
            "model_name": route["model_name"],
            "api_base": route["api_base"],
        },
        "suite_sha256": report["suite_sha256"],
        "law_manifest": {
            "path": LAW_MANIFEST.relative_to(REPO).as_posix(),
            "sha256": sha256(LAW_MANIFEST),
            "snapshot_date": law_manifest["download_snapshot_date"],
            "criminal_law_version": law_manifest["documents"]["xingfa"]["version_as_of"],
            "criminal_procedure_law_version": law_manifest["documents"]["xingsufa"]["version_as_of"],
        },
        "files": [
            {
                "path": path.relative_to(output).as_posix(),
                "bytes": path.stat().st_size,
                "sha256": sha256(path),
            }
            for path in sorted(set(all_files), key=lambda value: value.as_posix())
        ],
        "stage_order": [
            "Send only A阶段_独立判断包_DRAFT.zip",
            "Expert completes, signs and hashes the A-stage form",
            "Then disclose B阶段_差异核对包_DRAFT.zip",
            "If required, append revision/专家整改复签记录.pdf without overwriting old runs",
        ],
        "evidence_boundary": "Package preparation does not constitute expert review, signature, legal accuracy confirmation or publication approval",
    }
    write_json(output / "MANIFEST.json", root_manifest)

    summary = {
        "output": str(output),
        "pdf_count": len(list(output.rglob("*.pdf"))),
        "a_zip": {"path": str(a_zip), "sha256": sha256(a_zip), "bytes": a_zip.stat().st_size},
        "b_zip": {"path": str(b_zip), "sha256": sha256(b_zip), "bytes": b_zip.stat().st_size},
        "expert_review_complete": False,
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
