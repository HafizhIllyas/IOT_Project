"""Generate a clean A4 PDF version of the 3-member 2-minute presentation script."""

from __future__ import annotations

import html
from pathlib import Path
import re
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.platypus import (
    HRFlowable,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

BASE_DIR = Path(__file__).resolve().parent
MD_PATH = BASE_DIR / "docs" / "Presentation_Script_3_Members.md"
PDF_PATH = BASE_DIR / "docs" / "Presentation_Script_3_Members.pdf"


def sanitize_text(text: str) -> str:
    """Replace characters unsupported by standard PDF Helvetica while keeping ° and –."""
    text = text.replace("↻ Sync", "Sync")
    replacements = {
        "↻": "Sync",
        "→": "->",
        "−": "-",
        "≤": "<=",
    }
    for src, dst in replacements.items():
        text = text.replace(src, dst)
    return text


def md_to_rml(text: str) -> str:
    """
    Sanitize text, escape &, <, > first, and convert markdown **bold**, *italic*,
    and `code` into ReportLab Paragraph markup.
    """
    clean = html.escape(sanitize_text(text), quote=False)
    clean = re.sub(r"`([^`]+)`", r'<font face="Courier">\1</font>', clean)
    clean = re.sub(r"\*\*([^*]+)\*\*", r"<b>\1</b>", clean)
    clean = re.sub(r"(?<!\*)\*([^*]+)\*(?!\*)", r"<i>\1</i>", clean)
    return clean


def build_script_pdf(md_path: Path = MD_PATH, pdf_path: Path = PDF_PATH) -> Path:
    """Parse docs/Presentation_Script_3_Members.md and render an A4 PDF."""
    raw_lines = md_path.read_text(encoding="utf-8").splitlines()
    pdf_path.parent.mkdir(parents=True, exist_ok=True)

    doc = SimpleDocTemplate(
        str(pdf_path),
        pagesize=A4,
        leftMargin=2 * cm,
        rightMargin=2 * cm,
        topMargin=2 * cm,
        bottomMargin=2 * cm,
        title="TFB2093 IoT — 2-Minute Video Presentation Script (3 Members)",
    )

    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        "ScriptTitle",
        parent=styles["Title"],
        fontName="Helvetica-Bold",
        fontSize=15,
        leading=19,
        textColor=colors.HexColor("#0F172A"),
        alignment=0,
        spaceAfter=6,
    )
    meta_style = ParagraphStyle(
        "ScriptMeta",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=9.5,
        leading=13,
        textColor=colors.HexColor("#475569"),
        spaceAfter=8,
    )
    h2_style = ParagraphStyle(
        "SectionH2",
        parent=styles["Heading2"],
        fontName="Helvetica-Bold",
        fontSize=12,
        leading=16,
        textColor=colors.HexColor("#0F766E"),
        spaceBefore=8,
        spaceAfter=4,
    )
    bullet_style = ParagraphStyle(
        "ChecklistBullet",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=9.5,
        leading=13,
        leftIndent=14,
        firstLineIndent=-9,
        textColor=colors.HexColor("#1E293B"),
        spaceAfter=2.5,
    )
    cue_style = ParagraphStyle(
        "OnScreenCue",
        parent=styles["Normal"],
        fontName="Helvetica-Oblique",
        fontSize=9.0,
        leading=12.5,
        leftIndent=10,
        textColor=colors.HexColor("#475569"),
        spaceAfter=2,
    )
    quote_style = ParagraphStyle(
        "SpokenQuote",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=11,
        leading=15,
        textColor=colors.HexColor("#0F172A"),
    )

    story = [
        Paragraph(
            md_to_rml("TFB2093 IoT — 2-Minute Video Presentation Script (3 Members)"),
            title_style,
        )
    ]

    in_cue_block = False
    avail_width = A4[0] - 4 * cm

    for line in raw_lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("# "):
            continue
        if stripped == "---":
            in_cue_block = False
            story.append(Spacer(1, 3))
            story.append(HRFlowable(width="100%", thickness=0.6, color=colors.HexColor("#CBD5E1")))
            story.append(Spacer(1, 4))
            continue

        if stripped.startswith("## "):
            in_cue_block = False
            story.append(Paragraph(md_to_rml(stripped[3:]), h2_style))
            continue

        if stripped == "**[On Screen]**":
            in_cue_block = True
            story.append(Paragraph(md_to_rml("**[On Screen]**"), cue_style))
            continue

        if stripped.startswith("- "):
            item_rml = md_to_rml(stripped[2:])
            if in_cue_block:
                story.append(Paragraph(f"• {item_rml}", cue_style))
            else:
                story.append(Paragraph(f"• {item_rml}", bullet_style))
            continue

        if stripped.startswith("> "):
            in_cue_block = False
            quote_text = stripped[2:].strip()
            q_para = Paragraph(md_to_rml(quote_text), quote_style)
            box = Table([[q_para]], colWidths=[avail_width - 12])
            box.hAlign = "RIGHT"
            box.setStyle(
                TableStyle(
                    [
                        ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#F1F5F9")),
                        ("LINEBEFORE", (0, 0), (0, -1), 2.5, colors.HexColor("#0F766E")),
                        ("LEFTPADDING", (0, 0), (-1, -1), 10),
                        ("RIGHTPADDING", (0, 0), (-1, -1), 10),
                        ("TOPPADDING", (0, 0), (-1, -1), 7),
                        ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
                    ]
                )
            )
            story.append(Spacer(1, 3))
            story.append(box)
            story.append(Spacer(1, 4))
            continue

        story.append(Paragraph(md_to_rml(stripped), meta_style))

    doc.build(story)
    return pdf_path


if __name__ == "__main__":
    out = build_script_pdf()
    print(f"[OK] Generated script PDF: {out}")
