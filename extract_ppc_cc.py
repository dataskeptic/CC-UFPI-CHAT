#!/usr/bin/env python3
"""
extract_ppc_cc.py — Extract text and tables from the Projeto Pedagógico do Curso PDF
specifically tailored for the Computer Science PPC (Currículo 5 - 2019).

Features:
- Page-by-page extraction but chunks content by semantic headings (e.g. "1. INTRODUÇÃO")
- Uses font heuristics (Arial-BoldMT >= 11.5) to detect headings
- Extracts tables to Markdown format
- Outputs both .md and .txt files into a designated folder
"""

import fitz  # PyMuPDF
import re
from pathlib import Path
from datetime import datetime
from collections import defaultdict

# ── Configuration ─────────────────────────────────────────────────────────────
INPUT_PDF = Path("documentos_sigaa/Projeto Pedagógico do Curso (Currículo 5 - Criado em 2019).pdf")
OUTPUT_DIR = Path("extracted_ppc_cc")

HEADING_MIN_SIZE = 11.5
HEADING_FONT_KEYWORD = "Bold"

# ── Extraction Logic ──────────────────────────────────────────────────────────

def is_block_inside_tables(block_rect: fitz.Rect, table_bboxes: list[fitz.Rect]) -> bool:
    """Check if a text block overlaps significantly with any detected table."""
    for tb in table_bboxes:
        # If intersection area is > 50% of the block's area, consider it inside
        intersect = block_rect.intersect(tb)
        if not intersect.is_empty:
            if intersect.get_area() > 0.5 * block_rect.get_area():
                return True
    return False

def extract_text_from_dict_block(block: dict) -> tuple[str, bool]:
    """Reconstructs text from a dict block, unwraps paragraphs, and determines if it's a heading."""
    if "lines" not in block:
        return "", False

    # Heading detection
    is_heading = False
    first_span = None
    for line in block["lines"]:
        if line["spans"]:
            first_span = line["spans"][0]
            break
            
    raw_text = "".join(span["text"] for line in block["lines"] for span in line["spans"]).strip()
    
    if first_span:
        size = first_span.get("size", 0)
        font = first_span.get("font", "")
        if size >= HEADING_MIN_SIZE and HEADING_FONT_KEYWORD in font:
            if re.match(r"^\d+(\.\d+)*\s*[\.\-]?\s*[A-Z]", raw_text):
                is_heading = True
            else:
                keywords = ["APRESENTAÇÃO", "SUMÁRIO", "INTRODUÇÃO", "REFERÊNCIAS", "ANEXO", "EMENTÁRIO", "PERFIL", "OBJETIVO", "METODOLOGIA"]
                if any(raw_text.upper().startswith(k) for k in keywords):
                    is_heading = True

    # Reconstruct text with unwrapping
    lines_text = []
    for line in block["lines"]:
        line_str = "".join(span["text"] for span in line["spans"]).strip()
        if line_str:
            lines_text.append(line_str)
            
    unwrapped = []
    for i, line in enumerate(lines_text):
        if not unwrapped:
            unwrapped.append(line)
        else:
            prev = unwrapped[-1]
            if prev.endswith("-"):
                unwrapped[-1] = prev[:-1] + line
            elif prev[-1] in [".", ":", ";", "!", "?", "—", "”", '"', ")"]:
                unwrapped.append(line)
            else:
                unwrapped[-1] = prev + " " + line

    final_text = "\n".join(unwrapped).strip()
    return final_text, is_heading

def process_pdf(pdf_path: Path) -> dict:
    doc = fitz.open(str(pdf_path))
    
    # We will group content by headings
    # Dictionary maintaining insertion order (Python 3.7+)
    chunks = defaultdict(list)
    current_heading = "Início / Metadados"
    
    stats = {
        "total_pages": len(doc),
        "tables_found": 0,
        "headings_found": 0
    }

    for page_num, page in enumerate(doc, start=1):
        elements = [] # Tuples of (y0, type, content) where type is 'text', 'heading', or 'table'
        
        # 1. Extract tables
        table_bboxes = []
        try:
            finder = page.find_tables()
            for tab in finder.tables:
                try:
                    md = tab.to_markdown()
                    if md and "|" in md:
                        rect = fitz.Rect(tab.bbox)
                        table_bboxes.append(rect)
                        elements.append((rect.y0, "table", md))
                        stats["tables_found"] += 1
                except Exception:
                    pass
        except Exception:
            pass

        # 2. Extract text blocks
        page_dict = page.get_text("dict")
        for block in page_dict.get("blocks", []):
            if block.get("type") != 0: # not text
                continue
                
            block_rect = fitz.Rect(block.get("bbox", (0, 0, 0, 0)))
            if is_block_inside_tables(block_rect, table_bboxes):
                continue
                
            text, is_heading = extract_text_from_dict_block(block)
            if not text:
                continue
                
            # If it's a standalone number or a very short meaningless string, skip treating as heading
            if is_heading and len(text) < 3 and not text.isalpha():
                is_heading = False
                
            type_str = "heading" if is_heading else "text"
            elements.append((block_rect.y0, type_str, text))

        # 3. Sort elements by their vertical position to maintain reading order
        elements.sort(key=lambda x: x[0])
        
        # 4. Group into chunks
        for _, elem_type, content in elements:
            if elem_type == "heading":
                # Clean up heading text
                clean_heading = re.sub(r"\s+", " ", content).strip()
                if clean_heading:
                    current_heading = clean_heading
                    stats["headings_found"] += 1
            else:
                # Add to current chunk
                chunks[current_heading].append(content)
                
    doc.close()
    return chunks, stats

# ── Output Generation ─────────────────────────────────────────────────────────

def generate_markdown(chunks: dict, stats: dict) -> str:
    lines = [
        "---",
        'title: "Projeto Pedagógico do Curso de Bacharelado em Ciência da Computação"',
        'curriculum: "Currículo 5 - Criado em 2019"',
        f'total_pages: {stats["total_pages"]}',
        f'extracted_at: "{datetime.now().isoformat(timespec="seconds")}"',
        "---",
        ""
    ]
    
    for heading, contents in chunks.items():
        if not contents:
            continue
            
        lines.append(f"## {heading}")
        lines.append("")
        
        # Merge contents that are text fragments
        merged_contents = []
        for content in contents:
            if not merged_contents:
                merged_contents.append(content)
            else:
                prev = merged_contents[-1]
                # If it's a table, never merge
                if "|" in prev or "|" in content:
                    merged_contents.append(content)
                # If previous doesn't end in sentence terminator, and current doesn't start with list char
                elif prev and prev[-1] not in [".", ":", ";", "!", "?", "—", "”", '"', ")", "\n"] and not content.startswith(("-", "•")):
                    if prev.endswith("-"):
                        merged_contents[-1] = prev[:-1] + content
                    else:
                        merged_contents[-1] = prev + " " + content
                else:
                    merged_contents.append(content)
                    
        for content in merged_contents:
            lines.append(content)
            # Add blank line after blocks, unless it's a very short line that looks like continuation
            lines.append("")
            
    return "\n".join(lines)

def generate_txt(chunks: dict, stats: dict) -> str:
    lines = [
        "================================================================================",
        " PROJETO PEDAGÓGICO DO CURSO DE BACHARELADO EM CIÊNCIA DA COMPUTAÇÃO",
        " Currículo 5 - Criado em 2019",
        f" Total de páginas extraídas: {stats['total_pages']}",
        "================================================================================",
        ""
    ]
    
    for heading, contents in chunks.items():
        if not contents:
            continue
            
        lines.append(f"\n[ {heading.upper()} ]")
        lines.append("-" * 80)
        
        # Merge contents that are text fragments
        merged_contents = []
        for content in contents:
            if not merged_contents:
                merged_contents.append(content)
            else:
                prev = merged_contents[-1]
                # If it's a table, never merge
                if "|" in prev or "|" in content:
                    merged_contents.append(content)
                # If previous doesn't end in sentence terminator, and current doesn't start with list char
                elif prev and prev[-1] not in [".", ":", ";", "!", "?", "—", "”", '"', ")", "\n"] and not content.startswith(("-", "•")):
                    if prev.endswith("-"):
                        merged_contents[-1] = prev[:-1] + content
                    else:
                        merged_contents[-1] = prev + " " + content
                else:
                    merged_contents.append(content)
                    
        for content in merged_contents:
            lines.append(content)
            # only add an extra blank line if the content is substantial or a table
            if "|" in content or len(content) > 100:
                lines.append("")
            
    return "\n".join(lines)

def main():
    if not INPUT_PDF.exists():
        print(f"[ERRO] PDF não encontrado em: {INPUT_PDF}")
        return
        
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    
    print(f"Iniciando extração do PDF: {INPUT_PDF.name}")
    chunks, stats = process_pdf(INPUT_PDF)
    
    print(f"Extração concluída:")
    print(f"  - Páginas processadas : {stats['total_pages']}")
    print(f"  - Títulos detectados  : {stats['headings_found']}")
    print(f"  - Tabelas extraídas   : {stats['tables_found']}")
    
    md_content = generate_markdown(chunks, stats)
    txt_content = generate_txt(chunks, stats)
    
    md_path = OUTPUT_DIR / "ppc_cc_2019.md"
    txt_path = OUTPUT_DIR / "ppc_cc_2019.txt"
    
    md_path.write_text(md_content, encoding="utf-8")
    txt_path.write_text(txt_content, encoding="utf-8")
    
    print(f"\nArquivos gerados com sucesso:")
    print(f"  - {md_path}")
    print(f"  - {txt_path}")

if __name__ == "__main__":
    main()
