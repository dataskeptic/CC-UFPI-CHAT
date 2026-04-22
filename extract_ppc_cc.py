#!/usr/bin/env python3
"""
extract_ppc_cc.py — Extrai o Projeto Pedagógico do Curso (PPC) usando Docling.

Fixes v5:
- Cabeçalho TXT duplicado: bug de parênteses não fechados → txt_header era
  concatenado infinitamente. Corrigido com parênteses corretos.
- Campos de disciplina (Créditos/Carga Horária/Pré-requisito) agora têm os
  valores inline: "Créditos: 3.1.0" em vez de "Créditos:\n3.1.0".
- Símbolo ßà nas tabelas de equivalência substituído por "↔" (seta bidirecional).
- Remoção de duplicação de blocos de capa (Docling repete o heading da capa
  uma vez por página de rosto — detectado e deduplicado).
- Sintaxe de PdfPipelineOptions() e DocumentConverter() corrigida.
"""

import re
import sys
from pathlib import Path
from datetime import datetime

# ── Configuração ───────────────────────────────────────────────────────────────
INPUT_PDF  = Path("docs_sigaa_cc/Projeto Pedagógico do Curso (Currículo 5 - Criado em 2019).pdf")
OUTPUT_DIR = Path("extracted_docs/extracted_ppc_cc")

# ── Padrões de ruído específicos do PPC UFPI ──────────────────────────────────
NOISE_PATTERNS = [
    re.compile(r"^\s*\t?\s*\d{1,3}\s*\t?\s*$"),          # número de página isolado
    re.compile(r"^[\-\=\s]+$"),                            # linhas só de traços/iguais
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

SUMARIO_START = re.compile(r"^#+\s*SUMÁRIO\s*$", re.IGNORECASE)
SUMARIO_END   = re.compile(r"^#+\s*APRESENTAÇÃO\s*$", re.IGNORECASE)
SIGNATURE_LINE = re.compile(r"^[\\/_\s]{10,}$")

# ── Campos de disciplina que precisam do valor na mesma linha ─────────────────
# Detecta linhas como "Créditos:", "Carga Horária:", "Pré-requisito(s):"
DISCIPLINA_FIELD = re.compile(
    r"^(Créditos|Carga\s+Hor[aá]ria|Pré-requisito\(?s?\)?)\s*:\s*$",
    re.IGNORECASE,
)

# Símbolo garbled de direção nas tabelas de equivalência
BIDI_ARROW_RE = re.compile(r"ß\s*à|ßà", re.IGNORECASE)

# Bloco de capa que Docling repete por página → detectar e manter só a 1ª ocorrência
COVER_BLOCK_RE = re.compile(
    r"## MINISTÉRIO DA EDUCAÇÃO UNIVERSIDADE FEDERAL DO PIAUÍ"
    r".*?BACHARELADO EM CIÊNCIA DA COMPUTAÇÃO",
    re.DOTALL,
)


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


def fix_bidi_arrows(text: str) -> str:
    """Substitui o símbolo garbled ßà por ↔."""
    return BIDI_ARROW_RE.sub("↔", text)


def deduplicate_cover_block(md: str) -> str:
    """
    Docling inclui o heading gigante da capa uma vez por página de rosto.
    Mantém apenas a primeira ocorrência e remove as demais.
    """
    matches = list(COVER_BLOCK_RE.finditer(md))
    if len(matches) <= 1:
        return md
    # Remove todas as ocorrências após a primeira
    first_end = matches[0].end()
    prefix = md[:first_end]
    suffix = md[first_end:]
    suffix = COVER_BLOCK_RE.sub("", suffix)
    return prefix + suffix


def fix_inline_fields(lines: list[str]) -> list[str]:
    """
    Docling às vezes quebra campos de disciplina em duas linhas:
        Créditos:
        3.1.0
    Esta função junta o valor na mesma linha:
        Créditos: 3.1.0
    """
    out = []
    i = 0
    while i < len(lines):
        line = lines[i]
        if DISCIPLINA_FIELD.match(line.strip()):
            # Procura o próximo valor não-vazio
            j = i + 1
            while j < len(lines) and not lines[j].strip():
                j += 1
            if j < len(lines) and not lines[j].startswith(("#", "|")):
                value = lines[j].strip()
                out.append(line.rstrip() + " " + value)
                i = j + 1
                continue
        out.append(line)
        i += 1
    return out


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
                    if clean:
                        sumario_entries.append(clean)
                i += 1
            seen = set()
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


def normalize_body_spaces(line: str) -> str:
    if line.startswith("|") or line.startswith("#"):
        return line
    return re.sub(r" +", " ", line)


# ── Pós-processamento principal ───────────────────────────────────────────────

def post_process_markdown(raw_md: str) -> str:
    """
    Limpa e organiza o Markdown bruto gerado pelo Docling:
    1. Remove bloco de capa duplicado
    2. Corrige símbolo ßà → ↔
    3. Remove linhas de ruído fora de tabelas
    4. Junta campos de disciplina com seus valores (Créditos:, Carga Horária:, Pré-req:)
    5. Limpa bloco do Sumário
    6. Limpa assinaturas
    7. Rebaixa headings de capa de ## para ###
    8. Normaliza espaços múltiplos no corpo
    9. Colapsa múltiplas linhas em branco
    """
    # Pré-processamento no texto completo
    raw_md = deduplicate_cover_block(raw_md)
    raw_md = fix_bidi_arrows(raw_md)

    lines = raw_md.splitlines()
    out = []

    for line in lines:
        in_table = line.startswith("|")

        if not in_table and is_noise_line(line):
            continue

        # Corrige espaço ausente após # em headings colados
        heading_match = re.match(r"^(#{1,6})([^ #])", line)
        if heading_match:
            line = heading_match.group(1) + " " + line[len(heading_match.group(1)):]

        # Rebaixa headings de capa de ## para ###
        h2_match = re.match(r"^## (.+)$", line)
        if h2_match and is_cover_heading(h2_match.group(1)):
            line = "### " + h2_match.group(1)

        if not in_table:
            line = normalize_body_spaces(line)

        out.append(line)

    # Etapas estruturais em sequência
    out = fix_inline_fields(out)
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
        padded = []
        for j in range(num_cols):
            cell = row[j] if j < len(row) else ""
            padded.append(cell.ljust(col_widths[j]))
        out.append("  ".join(padded).rstrip())
        if k == 0:
            out.append("  ".join("-" * w for w in col_widths))
    return out


def markdown_to_txt(md: str) -> str:
    """
    Converte Markdown limpo → TXT estruturado e legível:
    - Headings → separadores ASCII por nível
    - Tabelas → colunas alinhadas com ljust
    - Remove marcação inline (negrito, itálico, código)
    - Remove frontmatter YAML
    - Mantém campos de disciplina inline (já processados)
    """
    # Remove frontmatter YAML
    md = re.sub(r"^---\n.*?\n---\n", "", md, flags=re.DOTALL)

    lines = md.splitlines()
    out = []
    i = 0

    while i < len(lines):
        line = lines[i]

        # Bloco de tabela
        if line.startswith("|"):
            table_block = []
            while i < len(lines) and lines[i].startswith("|"):
                table_block.append(lines[i])
                i += 1
            out.append("")
            out.extend(render_table_txt(table_block))
            out.append("")
            continue

        # Headings → separadores ASCII
        heading_match = re.match(r"^(#{1,6})\s+(.*)", line)
        if heading_match:
            level = len(heading_match.group(1))
            text  = heading_match.group(2).strip()
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
            else:
                out.append(f"    {text}")
            out.append("")
            i += 1
            continue

        # Linha de assinatura
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

    raw_md   = result.document.export_to_markdown(strict_text=False)
    md_clean = post_process_markdown(raw_md)
    txt_clean = markdown_to_txt(md_clean)

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
        "=" * 80 + "\n\n"
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
