from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

from PIL import Image, ImageChops, ImageStat, ImageDraw


HERE = Path(__file__).resolve().parent
SOURCE = HERE / "qa" / "screens"
RENDERED = HERE / "qa" / "pptx-render"
PPTX = HERE.parent / "星火智学_作品方案_技术主线V2_DRAFT.pptx"


def index(path: Path) -> int:
    matches = re.findall(r"\d+", path.stem)
    if not matches:
        raise ValueError(path)
    return int(matches[-1])


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    sources = sorted(SOURCE.glob("slide-*.png"), key=index)
    rendered = sorted(RENDERED.glob("*.PNG"), key=index)
    if len(sources) != 12 or len(rendered) != 12:
        raise SystemExit(f"Expected 12+12 images, got {len(sources)}+{len(rendered)}")
    rows = []
    thumbs = []
    for position, (left_path, right_path) in enumerate(zip(sources, rendered), start=1):
        left = Image.open(left_path).convert("RGB")
        right = Image.open(right_path).convert("RGB")
        if left.size != right.size:
            right = right.resize(left.size, Image.Resampling.LANCZOS)
        difference = ImageChops.difference(left, right)
        stat = ImageStat.Stat(difference)
        mean = round(sum(stat.mean) / 3, 6)
        rows.append(
            {
                "slide": position,
                "source": left_path.name,
                "rendered": right_path.name,
                "size": list(left.size),
                "mean_absolute_pixel_difference": mean,
                "source_sha256": sha(left_path),
                "rendered_sha256": sha(right_path),
            }
        )
        thumb = right.copy()
        thumb.thumbnail((384, 216), Image.Resampling.LANCZOS)
        thumbs.append(thumb)

    overview = Image.new("RGB", (384 * 3, 246 * 4), "#d9d9d9")
    draw = ImageDraw.Draw(overview)
    for idx, thumb in enumerate(thumbs):
        x = (idx % 3) * 384
        y = (idx // 3) * 246
        overview.paste(thumb, (x, y))
        draw.rectangle((x, y + 216, x + 384, y + 246), fill="#fafaf8")
        draw.text((x + 10, y + 222), f"SLIDE {idx + 1:02d}", fill="#0a0a0a")
    overview_path = HERE / "qa" / "pptx-overview.png"
    overview.save(overview_path)

    report = {
        "schema_version": "guizang-tech-v2-pptx-render-audit-v1",
        "pptx": PPTX.name,
        "pptx_bytes": PPTX.stat().st_size,
        "pptx_sha256": sha(PPTX),
        "slides": 12,
        "rendered_slides": 12,
        "under_100_mb": PPTX.stat().st_size < 100 * 1024 * 1024,
        "max_mean_absolute_pixel_difference": max(row["mean_absolute_pixel_difference"] for row in rows),
        "rows": rows,
        "overview": overview_path.name,
    }
    report_path = HERE / "qa" / "pptx-report.json"
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({key: report[key] for key in ("slides", "rendered_slides", "pptx_bytes", "under_100_mb", "max_mean_absolute_pixel_difference")}, ensure_ascii=False))


if __name__ == "__main__":
    main()
