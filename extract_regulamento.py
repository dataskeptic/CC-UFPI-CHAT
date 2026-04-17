#!/usr/bin/env python3
"""
extract_regulamento.py — Extract text from Regulamento Geral da Graduação PDF.

Features:
- Page-by-page extraction but chunks content by CAPÍTULO and TÍTULO.
- Uses font heuristics (Calibri >= 11.5) to detect headings.
- Unwraps paragraphs while respecting legal punctuation (`;`, `:`, `.`).
- Outputs both .md and .txt files into a designated folder.
"""

import fitz  # PyMuPDF
import re
from pathlib import Path
from datetime import datetime
from collections import defaultdict

# ── Configuration ─────────────────────────────────────────────────────────────
INPUT_PDF = Path("documentos_sigaa/Regulamento Geral da Graduação (Atualizado em 03 - 05 - 2023)")
OUTPUT_DIR = Path("extracted_regulamento")

HEADING_MIN_SIZE = 11.5

# ── Extraction Logic ──────────────────────────────────────────────────────────

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
        
        # Check if it starts with TÍTULO or CAPÍTULO and is large enough (to avoid Sumário)
        if size >= HEADING_MIN_SIZE:
            if re.match(r"^(TÍTULO|CAPÍTULO)\s+[IVXLCDM]+\s+-", raw_text, re.IGNORECASE):
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
    
    # Dictionary maintaining insertion order
    chunks = defaultdict(list)
    current_heading = "Início / Metadados"
    
    stats = {
        "total_pages": len(doc),
        "headings_found": 0
    }

    for page_num, page in enumerate(doc, start=1):
        elements = []
        
        # Extract text blocks
        page_dict = page.get_text("dict")
        for block in page_dict.get("blocks", []):
            if block.get("type") != 0: # not text
                continue
                
            block_rect = fitz.Rect(block.get("bbox", (0, 0, 0, 0)))
            text, is_heading = extract_text_from_dict_block(block)
            if not text:
                continue
                
            # Filter out simple page numbers
            if text.isdigit() and len(text) <= 3:
                continue
                
            type_str = "heading" if is_heading else "text"
            elements.append((block_rect.y0, type_str, text))

        # Sort elements by their vertical position to maintain reading order
        elements.sort(key=lambda x: x[0])
        
        # Group into chunks
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
        'title: "Regulamento Geral da Graduação"',
        'updated_at: "03-05-2023"',
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
        
        merged_contents = []
        for content in contents:
            if not merged_contents:
                merged_contents.append(content)
            else:
                prev = merged_contents[-1]
                # If previous doesn't end in sentence terminator, merge
                # Legal documents often use I -, a), etc.
                is_list_item = re.match(r"^([IVXLCDM]+\s*-|[a-z]\))", content)
                
                if prev and prev[-1] not in [".", ":", ";", "!", "?", "—", "”", '"', ")", "\n"] and not is_list_item:
                    if prev.endswith("-"):
                        merged_contents[-1] = prev[:-1] + content
                    else:
                        merged_contents[-1] = prev + " " + content
                else:
                    merged_contents.append(content)
                    
        for content in merged_contents:
            lines.append(content)
            lines.append("")
            
    return "\n".join(lines)

def generate_txt(chunks: dict, stats: dict) -> str:
    lines = [
        "================================================================================",
        " REGULAMENTO GERAL DA GRADUAÇÃO",
        " Atualizado em 03-05-2023",
        f" Total de páginas extraídas: {stats['total_pages']}",
        "================================================================================",
        ""
    ]
    
    for heading, contents in chunks.items():
        if not contents:
            continue
            
        lines.append(f"\n[ {heading.upper()} ]")
        lines.append("-" * 80)
        
        merged_contents = []
        for content in contents:
            if not merged_contents:
                merged_contents.append(content)
            else:
                prev = merged_contents[-1]
                is_list_item = re.match(r"^([IVXLCDM]+\s*-|[a-z]\))", content)
                
                if prev and prev[-1] not in [".", ":", ";", "!", "?", "—", "”", '"', ")", "\n"] and not is_list_item:
                    if prev.endswith("-"):
                        merged_contents[-1] = prev[:-1] + content
                    else:
                        merged_contents[-1] = prev + " " + content
                else:
                    merged_contents.append(content)
                    
        for content in merged_contents:
            lines.append(content)
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
    print(f"  - Títulos/Capítulos detectados: {stats['headings_found']}")
    
    md_content = generate_markdown(chunks, stats)
    txt_content = generate_txt(chunks, stats)
    
    md_path = OUTPUT_DIR / "regulamento_geral_2023.md"
    txt_path = OUTPUT_DIR / "regulamento_geral_2023.txt"
    
    md_path.write_text(md_content, encoding="utf-8")
    txt_path.write_text(txt_content, encoding="utf-8")
    
    print(f"\nArquivos gerados com sucesso:")
    print(f"  - {md_path}")
    print(f"  - {txt_path}")

if __name__ == "__main__":
    main()
