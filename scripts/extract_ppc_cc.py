#!/usr/bin/env python3
"""
extract_ppc_cc.py — Extrai o PPC do Curso de CC/UFPI usando Docling.
"""

import re
import sys
from pathlib import Path
from datetime import datetime

PROJECT_ROOT = Path(__file__).parent.parent
INPUT_PDF    = PROJECT_ROOT / "docs_sigaa_cc/Projeto Pedagógico do Curso (Currículo 5 - Criado em 2019).pdf"
OUTPUT_DIR   = PROJECT_ROOT / "extracted_text/extracted_ppc_cc"

# ── Padrões de ruído ───────────────────────────────────────────────────────────
NOISE_PATTERNS = [
    re.compile(r"^\s*\t?\s*\d{1,3}\s*\t?\s*$"),
    re.compile(r"^[\-\=\s]+$"),
    re.compile(r"^MINISTÉRIO DA EDUCAÇÃO\s*$"),
    re.compile(r"^UNIVERSIDADE FEDERAL DO PIAUÍ\s*$"),
    re.compile(r"^CAMPUS MINISTRO PETRÔNIO PORTELA\s*$"),
    re.compile(r"^CENTRO DE CIÊNCIAS DA NATUREZA\s*$"),
    re.compile(r"^BACHARELADO EM CIÊNCIA DA COMPUTAÇÃO\s*$"),
    re.compile(r"^Projeto Pedagógico do Curso de\s*$"),
    re.compile(r"^Bacharelado em Ciência da\s*$"),
    re.compile(r"^Computação, da Universidade\s*$"),
    re.compile(r"^Federal do Piauí.*Ministro\s*$"),
    re.compile(r"^Petrônio Portela.*município de\s*$"),
    re.compile(r"^Teresina, Piauí.*implementado\s*$"),
    re.compile(r"^em 2019\.2\.?\s*$"),
    re.compile(r"^TERESINA,?\s+JANEIRO DE 2019\.?\s*$"),
    re.compile(r"^\s*$"),
]

COVER_HEADING_PATTERNS = [
    re.compile(r"^(REITOR|VICE-REITORA?|PRÓ-REITOR)"),
    re.compile(r"^(DIRETOR|VICE-DIRETOR|COORDENADOR|SUBCOORDENADOR)"),
    re.compile(r"^(COMPOSIÇÃO DO|IDENTIFICAÇÃO D[AO]|NÚCLEO DOCENTE)"),
    re.compile(r"^(MARAÍSA|MARIA ROSÁLIA|MIRTES|LUCYANA|ROSA LINA|JOSÂNIA|ANA CAROLINE)"),
    re.compile(r"^Profa?\.?\s+Dr"),
]

SUMARIO_START  = re.compile(r"^#+\s*SUMÁRIO\s*$", re.IGNORECASE)
SUMARIO_END    = re.compile(r"^#+\s*APRESENTAÇÃO\s*$", re.IGNORECASE)
SIGNATURE_LINE = re.compile(r"^[\\/_ \s]{10,}$")

# Campo de disciplina que aparece ISOLADO em sua própria linha (sem valor)
DISCIPLINA_FIELD = re.compile(
    r"^(Créditos|Carga\s+Hor[aá]ria|Pré-requisito\(?s?\)?):\s*$",
    re.IGNORECASE,
)

BIDI_ARROW_RE = re.compile(r"ß\s*à|ßà", re.IGNORECASE)

COVER_BLOCK_RE = re.compile(
    r"## MINISTÉRIO DA EDUCAÇÃO UNIVERSIDADE FEDERAL DO PIAUÍ"
    r".*?BACHARELADO EM CIÊNCIA DA COMPUTAÇÃO",
    re.DOTALL,
)

MAIN_TITLE_RE = re.compile(
    r"^##\s+PROJETO PEDAGÓGICO DO CURSO DE BACHARELADO EM CIÊNCIA DA COMPUTAÇÃO\s*$",
    re.IGNORECASE,
)


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


def fix_bidi_arrows(text: str) -> str:
    return BIDI_ARROW_RE.sub("↔", text)


def remove_image_comments(text: str) -> str:
    return re.sub(r"<!--\s*image\s*-->", "", text)


def deduplicate_cover_block(md: str) -> str:
    matches = list(COVER_BLOCK_RE.finditer(md))
    if len(matches) <= 1:
        return md
    first_end = matches[0].end()
    prefix = md[:first_end]
    suffix = COVER_BLOCK_RE.sub("", md[first_end:])
    return prefix + suffix


def normalize_body_spaces(line: str) -> str:
    if line.startswith("|") or line.startswith("#"):
        return line
    return re.sub(r" +", " ", line)


# ── Correção dos blocos de disciplina ─────────────────────────────────────────
#
# O Docling gera os campos de disciplina em dois padrões problemáticos:
#
# Padrão A — campos misturados numa linha só, sem valores:
#   "Créditos: Carga Horária:"
#   "Pré-requisito(s): 2.2.0"
#   "60h"
#   "- Estruturas de Dados"
#
# Padrão B — campo isolado sem valor (já tratado pelo antigo fix_inline_fields):
#   "Créditos:"
#   "2.2.0"
#
# Esta função normaliza ambos os padrões para:
#   "Créditos: 2.2.0"
#   "Carga Horária: 60h"
#   "Pré-requisito(s): - Estruturas de Dados"

# Detecta linha com múltiplos campos colados (ex: "Créditos: Carga Horária:")
MULTI_FIELD_RE = re.compile(
    r"^(Créditos|Carga\s+Hor[aá]ria|Pré-requisito\(?s?\)?):.*"
    r"(Créditos|Carga\s+Hor[aá]ria|Pré-requisito\(?s?\)?):.*",
    re.IGNORECASE,
)

# Detecta qualquer linha que seja um campo de disciplina (com ou sem valor)
ANY_FIELD_RE = re.compile(
    r"^(Créditos|Carga\s+Hor[aá]ria|Pré-requisito\(?s?\)?):\s*(.*)",
    re.IGNORECASE,
)

# Valores reconhecíveis de crédito (ex: "2.2.0") e carga horária (ex: "60h")
CREDITO_RE   = re.compile(r"^\d+\.\d+\.\d+$")
CARGA_RE     = re.compile(r"^\d{2,3}h$", re.IGNORECASE)


def fix_discipline_blocks(lines: list[str]) -> list[str]:
    """
    Varre as linhas procurando blocos de campos de disciplina e os normaliza.
    Cada campo deve ficar numa linha com seu valor: "Campo: valor".
    """
    out = []
    i = 0
    while i < len(lines):
        line = lines[i]
        stripped = line.strip()

        # Caso 1: linha com múltiplos campos colados — inicia coleta do bloco
        # Caso 2: campo isolado sem valor (padrão antigo)
        is_multi  = bool(MULTI_FIELD_RE.match(stripped))
        is_single = bool(DISCIPLINA_FIELD.match(stripped))

        if not (is_multi or is_single):
            out.append(line)
            i += 1
            continue

        # Coleta até 8 linhas seguintes para montar o bloco completo
        block_lines = [stripped]
        j = i + 1
        while j < len(lines) and j < i + 8:
            nxt = lines[j].strip()
            # Para ao encontrar heading, linha de tabela, ou linha longa de texto
            if nxt.startswith(("#", "|")) or (len(nxt) > 80 and not ANY_FIELD_RE.match(nxt)):
                break
            # Para ao encontrar "EMENTA" (início do conteúdo da disciplina)
            if re.match(r"^ementa\b", nxt, re.IGNORECASE):
                break
            block_lines.append(nxt)
            j += 1

        # Extrai os valores do bloco
        full_text = " ".join(block_lines)

        credito = ""
        carga   = ""
        prereqs = []

        # Tenta extrair crédito: padrão N.N.N
        m = re.search(r"\b(\d+\.\d+\.\d+)\b", full_text)
        if m:
            credito = m.group(1)

        # Tenta extrair carga horária: padrão NNh ou NNN h
        m = re.search(r"\b(\d{2,3})\s*h\b", full_text, re.IGNORECASE)
        if m:
            carga = m.group(1) + "h"

        # Pré-requisitos: tudo após "Pré-requisito(s):" até fim do bloco
        m = re.search(r"Pré-requisito\(?s?\)?:\s*(.*)", full_text, re.IGNORECASE)
        if m:
            prereq_raw = m.group(1).strip()
            # Remove os valores de crédito e carga que podem ter sido capturados
            prereq_raw = re.sub(r"\b\d+\.\d+\.\d+\b", "", prereq_raw)
            prereq_raw = re.sub(r"\b\d{2,3}\s*h\b", "", prereq_raw, flags=re.IGNORECASE)
            prereq_raw = prereq_raw.strip(" -")
            # Linhas de pré-requisito extras (ex: "- Estruturas de Dados") no bloco
            for bl in block_lines:
                if bl.startswith("- ") and not ANY_FIELD_RE.match(bl) and not CREDITO_RE.match(bl.lstrip("- ")) and not CARGA_RE.match(bl.lstrip("- ")):
                    prereq_raw = prereq_raw + " " + bl if prereq_raw else bl
            prereq_raw = re.sub(r"\s{2,}", " ", prereq_raw).strip()

        # Emite os campos normalizados
        out.append(f"Créditos: {credito}")
        out.append(f"Carga Horária: {carga}")
        out.append(f"Pré-requisito(s): {prereq_raw if m else '- - - - -'}")

        i = j
    return out


# ── Limpeza da tabela do APÊNDICE III ─────────────────────────────────────────
#
# O Docling duplica colunas nessa tabela, gerando linhas como:
#   | Categoria | Categoria | Atividade | Atividade | CH | CH |
# Esta função opera no texto completo e colapsa colunas duplicadas.

def clean_appendix_table(md: str) -> str:
    def dedup_row(line: str) -> str:
        if not line.startswith("|"):
            return line
        # Linha separadora — mantém mas simplifica
        if re.match(r"^\|[\s\-\|:]+\|$", line):
            return line
        cells = [c.strip() for c in line.split("|")]
        cells = [c for c in cells if c != ""]
        # Remove células duplicadas consecutivas
        deduped = [cells[0]] if cells else []
        for c in cells[1:]:
            if c != deduped[-1]:
                deduped.append(c)
        return "| " + " | ".join(deduped) + " |"

    lines = md.splitlines()
    # Encontra o bloco do APÊNDICE III e aplica dedup só nele
    in_appendix = False
    out = []
    for line in lines:
        if re.match(r"^##\s+APÊNDICE III", line, re.IGNORECASE):
            in_appendix = True
        elif re.match(r"^##\s+", line) and in_appendix:
            in_appendix = False

        if in_appendix and line.startswith("|"):
            out.append(dedup_row(line))
        else:
            out.append(line)

    return "\n".join(out)


# ── Sumário ────────────────────────────────────────────────────────────────────

def clean_sumario(lines: list[str]) -> list[str]:
    out = []
    i = 0
    while i < len(lines):
        line = lines[i]
        if SUMARIO_START.match(line.strip()):
            out.append("## SUMÁRIO")
            out.append("")
            i += 1
            sumario_entries = []
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
                            sumario_entries.append(clean)
                elif l.strip() and not re.match(r"^[\-\s]+$", l):
                    clean = re.sub(r"\s{2,}", " ", l.strip())
                    if clean and not re.match(r"^\d{1,3}$", clean):
                        sumario_entries.append(clean)
                i += 1
            seen: set[str] = set()
            for entry in sumario_entries:
                if entry not in seen:
                    seen.add(entry)
                    out.append(f"- {entry}")
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


# ── Pós-processamento principal (MD) ─────────────────────────────────────────

def post_process_markdown(raw_md: str) -> str:
    raw_md = remove_image_comments(raw_md)
    raw_md = deduplicate_cover_block(raw_md)
    raw_md = fix_bidi_arrows(raw_md)

    lines = raw_md.splitlines()
    out = []
    main_title_removed = False

    for line in lines:
        in_table = line.startswith("|")

        if not main_title_removed and MAIN_TITLE_RE.match(line.strip()):
            main_title_removed = True
            continue

        if not in_table and is_noise_line(line):
            continue

        heading_match = re.match(r"^(#{1,6})([^ #])", line)
        if heading_match:
            line = heading_match.group(1) + " " + line[len(heading_match.group(1)):]

        h2_match = re.match(r"^## (.+)$", line)
        if h2_match and is_cover_heading(h2_match.group(1)):
            line = "### " + h2_match.group(1)

        if not in_table:
            line = normalize_body_spaces(line)

        out.append(line)

    out = fix_discipline_blocks(out)
    out = clean_sumario(out)
    out = clean_signatures(out)

    result = "\n".join(out)
    result = clean_appendix_table(result)
    result = re.sub(r"\n{3,}", "\n\n", result)
    return result.strip()


# ── Renderização TXT ──────────────────────────────────────────────────────────

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
        padded = [
            (row[j] if j < len(row) else "").ljust(col_widths[j])
            for j in range(num_cols)
        ]
        out.append("  ".join(padded).rstrip())
        if k == 0:
            out.append("  ".join("-" * w for w in col_widths))
    return out


def markdown_to_txt(md: str, strip_first_h1_title: bool = True) -> str:
    md = re.sub(r"^---\n.*?\n---\n", "", md, flags=re.DOTALL)

    lines = md.splitlines()
    out = []
    i = 0
    first_doc_title_skipped = False

    while i < len(lines):
        line = lines[i]

        if line.startswith("|"):
            table_block = []
            while i < len(lines) and lines[i].startswith("|"):
                table_block.append(lines[i])
                i += 1
            out.append("")
            out.extend(render_table_txt(table_block))
            out.append("")
            continue

        heading_match = re.match(r"^(#{1,6})\s+(.*)", line)
        if heading_match:
            level = len(heading_match.group(1))
            text  = heading_match.group(2).strip()
            text  = re.sub(r"\*\*(.+?)\*\*", r"\1", text)
            text  = re.sub(r"`(.+?)`",        r"\1", text)

            if strip_first_h1_title and not first_doc_title_skipped and level <= 2:
                upper = text.upper()
                if "PROJETO PEDAGÓGICO" in upper and "CIÊNCIA DA COMPUTAÇÃO" in upper:
                    first_doc_title_skipped = True
                    i += 1
                    continue

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
            else:
                out.append(f"    {text}")
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
    print("Na primeira execução, modelos ML são baixados (~500 MB).")
    print("Tempo estimado: 3–8 min (1ª vez) / 1–3 min (execuções seguintes)\n")

    result = converter.convert(str(pdf_path))
    return result


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
    txt_clean = markdown_to_txt(md_clean, strip_first_h1_title=True)

    now = datetime.now().isoformat(timespec="seconds")

    md_header = (
        "---\n"
        'title: "Projeto Pedagógico do Curso de Bacharelado em Ciência da Computação"\n'
        'curriculum: "Currículo 5 - Criado em 2019"\n'
        'institution: "Universidade Federal do Piauí (UFPI)"\n'
        f'extracted_at: "{now}"\n'
        'extractor: "docling+tableformer-accurate"\n'
        "---\n\n"
    )

    txt_header = (
        "=" * 80 + "\n"
        "  PROJETO PEDAGÓGICO DO CURSO — BACHARELADO EM CIÊNCIA DA COMPUTAÇÃO\n"
        "  Currículo 5 — Criado em 2019 | UFPI\n"
        f"  Extraído em: {now} | Docling (TableFormer Accurate)\n"
        + "=" * 80 + "\n\n"
    )

    final_md  = md_header + md_clean
    final_txt = txt_header + txt_clean

    md_path  = OUTPUT_DIR / "ppc_cc_2019.md"
    txt_path = OUTPUT_DIR / "ppc_cc_2019.txt"

    md_path.write_text(final_md,  encoding="utf-8")
    txt_path.write_text(final_txt, encoding="utf-8")

    print(f"""
Arquivos gerados:
  {md_path}  ({len(final_md):,} chars)
  {txt_path} ({len(final_txt):,} chars)
""")


if __name__ == "__main__":
    main()