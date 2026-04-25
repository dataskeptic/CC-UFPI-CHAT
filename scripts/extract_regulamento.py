#!/usr/bin/env python3
"""
extract_regulamento.py — Extrai o Regulamento Geral da Graduação da UFPI usando Docling.

Características do documento:
- Estrutura jurídica: Títulos → Capítulos → Artigos → Parágrafos/Incisos
- Sem tabelas de disciplinas (sem campos Créditos/CH/Pré-req)
- Cabeçalho institucional repetido em várias páginas
- Numeração de página isolada em linhas
- Assinaturas ao final
"""

import re
import sys
from pathlib import Path
from datetime import datetime

# ── Configuração ───────────────────────────────────────────────────────────────
PROJECT_ROOT = Path(__file__).parent.parent
INPUT_PDF  = PROJECT_ROOT / "docs_sigaa_cc/Regulamento Geral da Graduação (Atualizado em 03 - 05 - 2023)"
OUTPUT_DIR = PROJECT_ROOT / "extracted_text/extracted_regulamento/"

# ── Padrões de ruído ──────────────────────────────────────────────────────────
NOISE_PATTERNS = [
    re.compile(r"^\s*\d{1,3}\s*$"),                          # número de página isolado
    re.compile(r"^[\-\=\s]+$"),                               # linhas de traço/igual
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

# Headings de capa/institucional que devem ser rebaixados de ## para ###
COVER_HEADING_PATTERNS = [
    re.compile(r"^(REITOR|VICE-REITORA?|PRÓ-REITOR)"),
    re.compile(r"^(PRESIDENTE|VICE-PRESIDENTE|SECRET[AÁ]RIO|CONSELHEIRO)"),
    re.compile(r"^(COMPOSIÇÃO|IDENTIFICAÇÃO|MEMBROS|REPRESENTANTE)"),
    re.compile(r"^Profa?\.?\s+Dr"),
]

# Assinaturas
SIGNATURE_LINE = re.compile(r"^[\\/_\s]{10,}$")

# Cabeçalho institucional repetido por página (deduplicar)
COVER_BLOCK_RE = re.compile(
    r"(## MINISTÉRIO DA EDUCAÇÃO UNIVERSIDADE FEDERAL DO PIAUÍ"
    r"|## CONSELHO DE ENSINO[,\s]PESQUISA E EXTENSÃO"
    r"|## UNIVERSIDADE FEDERAL DO PIAUÍ\s*\n)",
    re.IGNORECASE,
)

# Detecta início/fim do Sumário (se existir)
SUMARIO_START = re.compile(r"^#+\s*SUM[AÁ]RIO\s*$", re.IGNORECASE)
SUMARIO_END   = re.compile(r"^#+\s*(APRESENTAÇÃO|TÍTULO|CAPÍTULO|Art\.)\s*", re.IGNORECASE)


# ── Helpers ───────────────────────────────────────────────────────────────────

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


def deduplicate_cover_blocks(md: str) -> str:
    """
    Remove repetições do bloco de cabeçalho institucional que Docling gera
    uma vez por página. Mantém só a primeira ocorrência de cada padrão.
    """
    seen = set()
    lines = md.splitlines()
    out = []
    for line in lines:
        key = line.strip()
        if COVER_BLOCK_RE.match(line):
            if key in seen:
                continue
            seen.add(key)
        out.append(line)
    return "\n".join(out)


def clean_sumario(lines: list[str]) -> list[str]:
    """Se existir Sumário como tabela bagunçada, converte em lista plain-text."""
    out = []
    i = 0
    while i < len(lines):
        line = lines[i]
        if SUMARIO_START.match(line.strip()):
            out.append("## SUMÁRIO")
            out.append("")
            i += 1
            entries = []
            while i < len(lines):
                l = lines[i]
                if SUMARIO_END.match(l.strip()):
                    break
                if l.startswith("|"):
                    cells = [c.strip() for c in l.split("|") if c.strip()]
                    for cell in cells:
                        clean = re.sub(r"-{3,}", "", cell).strip()
                        clean = re.sub(r"\s{2,}", " ", clean)
                        if clean and not re.match(r"^\d{1,3}$", clean):
                            entries.append(clean)
                elif l.strip() and not re.match(r"^[\-\s]+$", l):
                    clean = re.sub(r"\s{2,}", " ", l.strip())
                    if clean:
                        entries.append(clean)
                i += 1
            seen = set()
            for e in entries:
                if e not in seen:
                    seen.add(e)
                    out.append(f"- {e}")
            out.append("")
        else:
            out.append(line)
            i += 1
    return out


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


def normalize_body_spaces(line: str) -> str:
    if line.startswith("|") or line.startswith("#"):
        return line
    return re.sub(r" {2,}", " ", line)


def fix_artigo_inline(lines: list[str]) -> list[str]:
    """
    Documentos jurídicos às vezes têm o número do artigo separado do texto:
        Art. 42.
        Disciplina é o conjunto...
    Junta numa única linha: "Art. 42. Disciplina é o conjunto..."
    """
    out = []
    i = 0
    art_re = re.compile(r"^(Art\.\s*\d+[\.\-º]?)\s*$")
    while i < len(lines):
        line = lines[i]
        m = art_re.match(line.strip())
        if m:
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


# ── Pós-processamento principal ───────────────────────────────────────────────

def post_process_markdown(raw_md: str) -> str:
    raw_md = deduplicate_cover_blocks(raw_md)

    lines = raw_md.splitlines()
    out = []

    for line in lines:
        in_table = line.startswith("|")

        if not in_table and is_noise_line(line):
            continue

        # Corrige heading colado sem espaço ("##Título")
        hm = re.match(r"^(#{1,6})([^ #])", line)
        if hm:
            line = hm.group(1) + " " + line[len(hm.group(1)):]

        # Rebaixa headings de capa de ## para ###
        h2 = re.match(r"^## (.+)$", line)
        if h2 and is_cover_heading(h2.group(1)):
            line = "### " + h2.group(1)

        if not in_table:
            line = normalize_body_spaces(line)

        out.append(line)

    out = fix_artigo_inline(out)
    out = clean_sumario(out)
    out = clean_signatures(out)

    result = "\n".join(out)
    result = re.sub(r"\n{3,}", "\n\n", result)
    return result.strip()


# ── Renderização TXT ─────────────────────────────────────────────────────────

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
    num_cols = max(len(r) for r in rows)
    col_widths = [0] * num_cols
    for row in rows:
        for j, cell in enumerate(row):
            if j < num_cols:
                col_widths[j] = max(col_widths[j], len(cell))
    out = []
    for k, row in enumerate(rows):
        padded = [row[j].ljust(col_widths[j]) if j < len(row) else " " * col_widths[j]
                  for j in range(num_cols)]
        out.append("  ".join(padded).rstrip())
        if k == 0:
            out.append("  ".join("-" * w for w in col_widths))
    return out


def markdown_to_txt(md: str) -> str:
    md = re.sub(r"^---\n.*?\n---\n", "", md, flags=re.DOTALL)

    lines = md.splitlines()
    out = []
    i = 0

    while i < len(lines):
        line = lines[i]

        # Tabela
        if line.startswith("|"):
            block = []
            while i < len(lines) and lines[i].startswith("|"):
                block.append(lines[i])
                i += 1
            out.append("")
            out.extend(render_table_txt(block))
            out.append("")
            continue

        # Headings → separadores ASCII
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

        # Assinatura
        if line.strip() == "---":
            out.append("  " + "_" * 50)
            i += 1
            continue

        # Remove marcação inline
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


# ── Conversão Docling ─────────────────────────────────────────────────────────

def convert(pdf_path: Path):
    try:
        from docling.document_converter import DocumentConverter, PdfFormatOption
        from docling.datamodel.base_models import InputFormat
        from docling.datamodel.pipeline_options import PdfPipelineOptions, TableFormerMode
    except ImportError:
        print("[ERRO] Docling não instalado. Execute: pip install docling")
        sys.exit(1)

    print("Configurando pipeline Docling (TableFormer ACCURATE)...")

    pipeline_options = PdfPipelineOptions(
        do_ocr=False,
        do_table_structure=True,
    )
    pipeline_options.table_structure_options.mode = TableFormerMode.ACCURATE
    pipeline_options.table_structure_options.do_cell_matching = True

    converter = DocumentConverter(
        format_options={
            InputFormat.PDF: PdfFormatOption(pipeline_options=pipeline_options)
        }
    )

    print(f"Convertendo: {pdf_path.name}")
    print("Tempo estimado: 1–3 min\n")

    return converter.convert(str(pdf_path))


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    if not INPUT_PDF.exists():
        print(f"[ERRO] PDF não encontrado: {INPUT_PDF}")
        print("Ajuste a variável INPUT_PDF no início deste script.")
        sys.exit(1)

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    result = convert(INPUT_PDF)
    print("Conversão concluída. Aplicando pós-processamento...")

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
        "  Atualizado em: 03/05/2023\n"
        f"  Extraído em: {now} | Docling (TableFormer Accurate)\n"
        "=" * 80 + "\n\n"
    )

    final_md  = md_header  + md_clean
    final_txt = txt_header + txt_clean

    stem     = INPUT_PDF.stem  # "Regulamento-Geral-da-Graduacao-Atualizado-em-03-05-2023"
    md_path  = OUTPUT_DIR / f"{stem}.md"
    txt_path = OUTPUT_DIR / f"{stem}.txt"

    md_path.write_text(final_md,  encoding="utf-8")
    txt_path.write_text(final_txt, encoding="utf-8")

    print(f"""
Arquivos gerados:
  {md_path}  ({len(final_md):,} chars)
  {txt_path} ({len(final_txt):,} chars)
""")


if __name__ == "__main__":
    main()
