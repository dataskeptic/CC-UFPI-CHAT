#!/usr/bin/env python3
"""
extract_regulamento.py — Extracts UFPI Graduation Regulation using Docling.

Document characteristics:
- Legal structure: Títulos → Capítulos → Artigos → Parágrafos/Incisos
- Institutional header repeated on every page
- Isolated page numbers
- Signatures at the end
"""

import re
import sys
from pathlib import Path
from datetime import datetime

# ── Configuration ──────────────────────────────────────────────────────────────
PROJECT_ROOT = Path(__file__).parent.parent
INPUT_PDF  = PROJECT_ROOT / "docs_sigaa_cc/Regulamento Geral da Graduação (Atualizado em 03 - 05 - 2023).pdf"
OUTPUT_DIR = PROJECT_ROOT / "extracted_text/extracted_regulamento"

# ── Noise patterns ─────────────────────────────────────────────────────────────
NOISE_PATTERNS = [
    re.compile(r"^\s*\d{1,3}\s*$"),
    re.compile(r"^[\-\=\s]+$"),
    re.compile(r"^MINISTÉRIO DA EDUCAÇÃO\s*$"),
    re.compile(r"^UNIVERSIDADE FEDERAL DO PIAUÍ\s*$"),
    re.compile(r"^CAMPUS MINISTRO PETRÔNIO PORTELA\s*$"),
    re.compile(r"^CONSELHO DE ENSINO[,\s]+PESQUISA E EXTENSÃO\s*$"),
    re.compile(r"^CEPEX\s*$"),
    re.compile(r"^REGULAMENTO GERAL DA GRADUAÇÃO\s*$"),
    re.compile(r"^Atualizado em\s+\d{2}/\d{2}/\d{4}\s*$"),
    re.compile(r"^TERESINA,?\s+\w+\s+DE\s+\d{4}\.?\s*$", re.IGNORECASE),
    re.compile(r"^\s*$"),
]

# Cover/institutional headings to demote from ## to ###
COVER_HEADING_PATTERNS = [
    re.compile(r"^(REITOR|VICE-REITORA?|PRÓ-REITOR)"),
    re.compile(r"^(PRESIDENTE|VICE-PRESIDENTE|SECRET[AÁ]RIO|CONSELHEIRO)"),
    re.compile(r"^(COMPOSIÇÃO|IDENTIFICAÇÃO|MEMBROS|REPRESENTANTE)"),
    re.compile(r"^Profa?\.?\s+Dr"),
]

SIGNATURE_LINE = re.compile(r"^[\\/_ \s]{10,}$")

# Repeated institutional heading that Docling emits once per page
REPEATED_HEADING_RE = re.compile(
    r"^## (MINISTÉRIO DA EDUCAÇÃO|UNIVERSIDADE FEDERAL DO PIAUÍ"
    r"|CONSELHO DE ENSINO|RESOLUÇÃO Nº 177)",
    re.IGNORECASE,
)

SUMARIO_START = re.compile(r"^#+\s*SUM[AÁ]RIO\s*$", re.IGNORECASE)
SUMARIO_END   = re.compile(r"^#+\s*(APRESENTAÇÃO|TÍTULO\s+I\b|Art\.)\s*", re.IGNORECASE)

# Art. with ordinal or period, isolated on its own line
ART_ALONE_RE  = re.compile(r"^(Art\.\s*\d+[ºª°\.]?)\s*$")

# Incisos/paragraphs that Docling sometimes breaks across lines
# e.g. "I\n- text" or "§ 1º\ntext"
INCISO_ALONE_RE = re.compile(r"^(I{1,3}V?|VI{0,3}|IX|X{1,3})\s*[-–]\s*$")


# ── Helpers ────────────────────────────────────────────────────────────────────

def is_noise_line(line: str) -> bool:
    stripped = line.strip()
    if not stripped:
        return True
    for pat in NOISE_PATTERNS:
        if pat.match(stripped):
            return True
    return False


def is_cover_heading(text: str) -> bool:
    for pat in COVER_HEADING_PATTERNS:
        if pat.match(text.strip()):
            return True
    return False


def normalize_body_spaces(line: str) -> str:
    if line.startswith("|") or line.startswith("#"):
        return line
    return re.sub(r" {2,}", " ", line)


# ── Deduplication of repeated institutional headings ──────────────────────────

def deduplicate_repeated_headings(lines: list[str]) -> list[str]:
    """
    Docling emits the document header (Resolução, Ministério, etc.) once
    per page. Keep only the first occurrence of each such heading.
    """
    seen: set[str] = set()
    out = []
    for line in lines:
        if REPEATED_HEADING_RE.match(line):
            key = line.strip()
            if key in seen:
                continue
            seen.add(key)
        out.append(line)
    return out


# ── Sumário cleanup ────────────────────────────────────────────────────────────

def clean_sumario(lines: list[str]) -> list[str]:
    """
    Converts the Sumário (often a messy table or dotted list from the PDF)
    into a clean bullet list, stripping dot leaders and page numbers.
    """
    out = []
    i = 0
    while i < len(lines):
        line = lines[i]
        if SUMARIO_START.match(line.strip()):
            out.append("## SUMÁRIO")
            out.append("")
            i += 1
            entries: list[str] = []
            pending = ""
            while i < len(lines):
                l = lines[i]
                if SUMARIO_END.match(l.strip()):
                    break

                # Extract text from table cells
                if l.startswith("|"):
                    cells = [c.strip() for c in l.split("|") if c.strip()]
                    raw = " ".join(cells)
                else:
                    raw = l.strip()

                if not raw or re.match(r"^[\-\s]+$", raw):
                    i += 1
                    continue

                # Strip dot leaders (sequences of 4+ dots) and trailing page numbers
                raw = re.sub(r"\.{4,}", "", raw)
                raw = re.sub(r"\s+\d{1,3}\s*$", "", raw).strip()
                raw = re.sub(r"\s{2,}", " ", raw)

                if not raw or re.match(r"^\d{1,3}$", raw):
                    i += 1
                    continue

                # Join continuation lines: if the line starts with a lowercase
                # letter or doesn't look like a new entry, it's a continuation
                if pending and (raw[0].islower() or raw.startswith("Férias") or raw.startswith("Especiais")):
                    pending = pending.rstrip() + " " + raw
                else:
                    if pending:
                        entries.append(pending)
                    pending = raw

                i += 1

            if pending:
                entries.append(pending)

            seen: set[str] = set()
            for e in entries:
                if e not in seen:
                    seen.add(e)
                    out.append(f"- {e}")
            out.append("")
        else:
            out.append(line)
            i += 1
    return out


# ── Join isolated Art. N. with next line ──────────────────────────────────────

def fix_artigo_inline(lines: list[str]) -> list[str]:
    """
    Joins 'Art. 42.' on its own line with the following text line.
    Also handles 'Art. 1º', 'Art. 10.', etc.
    """
    out = []
    i = 0
    while i < len(lines):
        line = lines[i]
        if ART_ALONE_RE.match(line.strip()):
            j = i + 1
            while j < len(lines) and not lines[j].strip():
                j += 1
            if j < len(lines) and not lines[j].startswith(("#", "|")):
                out.append(line.rstrip() + " " + lines[j].strip())
                i = j + 1
                continue
        out.append(line)
        i += 1
    return out


# ── Join isolated Roman numeral incisos with next line ────────────────────────

def fix_inciso_inline(lines: list[str]) -> list[str]:
    """
    Joins 'I -' alone on a line with the following text.
    Docling sometimes breaks 'I - texto do inciso' into two lines.
    """
    out = []
    i = 0
    while i < len(lines):
        line = lines[i]
        if INCISO_ALONE_RE.match(line.strip()):
            j = i + 1
            while j < len(lines) and not lines[j].strip():
                j += 1
            if j < len(lines) and not lines[j].startswith(("#", "|")):
                out.append(line.rstrip() + " " + lines[j].strip())
                i = j + 1
                continue
        out.append(line)
        i += 1
    return out


# ── Signatures ────────────────────────────────────────────────────────────────

def clean_signatures(lines: list[str]) -> list[str]:
    out = []
    prev_was_sig = False
    for line in lines:
        if SIGNATURE_LINE.match(line.strip()) or re.match(r"^[\\]{5,}", line):
            if not prev_was_sig:
                out.append("")
                out.append("---")
            prev_was_sig = True
        else:
            prev_was_sig = False
            out.append(line)
    return out


# ── Main post-processing ──────────────────────────────────────────────────────

def post_process_markdown(raw_md: str) -> str:
    # Remove <!-- image --> markers
    raw_md = re.sub(r"<!--\s*image\s*-->", "", raw_md)

    lines = raw_md.splitlines()
    out = []

    for line in lines:
        in_table = line.startswith("|")

        if not in_table and is_noise_line(line):
            continue

        # Fix heading missing space after # (e.g. "##Título")
        hm = re.match(r"^(#{1,6})([^ #])", line)
        if hm:
            line = hm.group(1) + " " + line[len(hm.group(1)):]

        # Demote cover headings from ## to ###
        h2 = re.match(r"^## (.+)$", line)
        if h2 and is_cover_heading(h2.group(1)):
            line = "### " + h2.group(1)

        if not in_table:
            line = normalize_body_spaces(line)

        out.append(line)

    out = deduplicate_repeated_headings(out)
    out = fix_artigo_inline(out)
    out = fix_inciso_inline(out)
    out = clean_sumario(out)
    out = clean_signatures(out)

    result = "\n".join(out)
    result = re.sub(r"\n{3,}", "\n\n", result)
    return result.strip()


# ── TXT rendering ─────────────────────────────────────────────────────────────

def render_table_txt(table_lines: list[str]) -> list[str]:
    rows = []
    for line in table_lines:
        if re.match(r"^\|[\s\-\|:]+\|$", line):
            continue
        cells = [c.strip() for c in line.split("|")]
        cells = [c for c in cells if c != ""]
        if cells:
            rows.append(cells)
    if not rows:
        return []

    num_cols   = max(len(r) for r in rows)
    col_widths = [0] * num_cols
    for row in rows:
        for j, cell in enumerate(row):
            if j < num_cols:
                col_widths[j] = max(col_widths[j], len(cell))

    out = []
    for k, row in enumerate(rows):
        padded = [
            (row[j] if j < len(row) else "").ljust(col_widths[j])
            for j in range(num_cols)
        ]
        out.append("  ".join(padded).rstrip())
        if k == 0:
            out.append("  ".join("-" * w for w in col_widths))
    return out


def markdown_to_txt(md: str) -> str:
    md = re.sub(r"^---\n.*?\n---\n", "", md, flags=re.DOTALL)

    lines = md.splitlines()
    out   = []
    i     = 0

    while i < len(lines):
        line = lines[i]

        if line.startswith("|"):
            block = []
            while i < len(lines) and lines[i].startswith("|"):
                block.append(lines[i])
                i += 1
            out.append("")
            out.extend(render_table_txt(block))
            out.append("")
            continue

        hm = re.match(r"^(#{1,6})\s+(.*)", line)
        if hm:
            level = len(hm.group(1))
            text  = hm.group(2).strip()
            text  = re.sub(r"\*\*(.+?)\*\*", r"\1", text)
            text  = re.sub(r"`(.+?)`",        r"\1", text)
            out.append("")
            if level == 1:
                out.append("=" * 80)
                out.append(f"  {text.upper()}")
                out.append("=" * 80)
            elif level == 2:
                out.append("=" * 80)
                out.append(f"  {text.upper()}")
                out.append("-" * 80)
            elif level == 3:
                out.append(f"  ▸ {text}")
                out.append("  " + "-" * (len(text) + 4))
            elif level == 4:
                out.append(f"    ◦ {text}")
            else:
                out.append(f"      {text}")
            out.append("")
            i += 1
            continue

        if line.strip() == "---":
            out.append("  " + "_" * 50)
            i += 1
            continue

        line = re.sub(r"\*\*(.+?)\*\*", r"\1", line)
        line = re.sub(r"\*(.+?)\*",     r"\1", line)
        line = re.sub(r"__(.+?)__",     r"\1", line)
        line = re.sub(r"_(.+?)_",       r"\1", line)
        line = re.sub(r"`(.+?)`",       r"\1", line)

        out.append(line)
        i += 1

    result = "\n".join(out)
    result = re.sub(r"\n{3,}", "\n\n", result)
    return result.strip()


# ── Docling conversion ────────────────────────────────────────────────────────

def convert(pdf_path: Path):
    try:
        from docling.document_converter import DocumentConverter, PdfFormatOption
        from docling.datamodel.base_models import InputFormat
        from docling.datamodel.pipeline_options import PdfPipelineOptions, TableFormerMode
    except ImportError:
        print("[ERROR] Docling not installed. Run: pip install docling")
        sys.exit(1)

    print("Configuring Docling pipeline (TableFormer ACCURATE)...")
    pipeline_options = PdfPipelineOptions(do_ocr=False, do_table_structure=True)
    pipeline_options.table_structure_options.mode = TableFormerMode.ACCURATE
    pipeline_options.table_structure_options.do_cell_matching = True

    converter = DocumentConverter(
        format_options={InputFormat.PDF: PdfFormatOption(pipeline_options=pipeline_options)}
    )

    print(f"Converting: {pdf_path.name}")
    print("Estimated time: 1–3 min\n")
    return converter.convert(str(pdf_path))


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    if not INPUT_PDF.exists():
        print(f"[ERROR] PDF not found: {INPUT_PDF}")
        sys.exit(1)

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    result = convert(INPUT_PDF)
    print("Conversion done. Applying post-processing...")

    raw_md    = result.document.export_to_markdown(strict_text=False)
    md_clean  = post_process_markdown(raw_md)
    txt_clean = markdown_to_txt(md_clean)

    now = datetime.now().isoformat(timespec="seconds")

    md_header = (
        "---\n"
        'title: "Regulamento Geral da Graduação da UFPI"\n'
        'institution: "Universidade Federal do Piauí (UFPI)"\n'
        'updated: "03/05/2023"\n'
        f'extracted_at: "{now}"\n'
        'extractor: "docling+tableformer-accurate"\n'
        "---\n\n"
    )

    txt_header = (
        "=" * 80 + "\n"
        "  REGULAMENTO GERAL DA GRADUAÇÃO\n"
        "  Universidade Federal do Piauí (UFPI)\n"
        "  Updated: 03/05/2023\n"
        f"  Extracted at: {now} | Docling (TableFormer Accurate)\n"
        + "=" * 80 + "\n\n"
    )

    stem     = INPUT_PDF.stem
    md_path  = OUTPUT_DIR / f"{stem}.md"
    txt_path = OUTPUT_DIR / f"{stem}.txt"

    md_path.write_text(md_header + md_clean,   encoding="utf-8")
    txt_path.write_text(txt_header + txt_clean, encoding="utf-8")

    print(f"""
Files generated:
  {md_path}  ({len(md_header + md_clean):,} chars)
  {txt_path} ({len(txt_header + txt_clean):,} chars)
""")


if __name__ == "__main__":
    main()