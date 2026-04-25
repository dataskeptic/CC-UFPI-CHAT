#!/usr/bin/env python3
"""
extract_fluxograma.py — Extract the curriculum flowchart into a structured dependency graph.
"""

import fitz
import re
from pathlib import Path
from datetime import datetime

PROJECT_ROOT = Path(__file__).parent.parent
INPUT_PDF = PROJECT_ROOT / "docs_sigaa_cc/Fluxograma Curricular do Curso (Currículo 5 - Criado em 2019).pdf"
OUTPUT_DIR = PROJECT_ROOT / "extracted_text/extracted_fluxograma"

def parse_blocks(blocks):
    disciplines = {}
    
    # First pass: collect raw data
    i = 0
    while i < len(blocks):
        text = blocks[i][4].strip()
        
        # Is it a 2 digit ID?
        if len(text) == 2 and text.isdigit():
            course_id = text
            
            # Look at next block
            next_block = blocks[i+1][4].strip()
            
            if re.match(r"^\d+\s*\(", next_block):
                # Name is missing (like ID 44 or 45)
                # Hardcoded fallbacks based on context
                if course_id == "44":
                    name = "Trabalho de Conclusão de Curso II"
                elif course_id == "45":
                    name = "Optativa"
                else:
                    name = "[Nome Ausente]"
                
                ch_prereq_raw = next_block.replace("\n", " ").strip()
                # Split CH and prereq: e.g. "60 (4) 38" or "60 (4) -"
                match = re.match(r"(.*? \(\d+\))\s+(.*)", ch_prereq_raw)
                if match:
                    ch = match.group(1).strip()
                    prereqs = match.group(2).strip()
                else:
                    ch = ch_prereq_raw
                    prereqs = "-"
                i += 2
            else:
                # Name is present
                name = next_block.replace("\n", " ").strip()
                
                # The next block should be CH and Prereqs
                ch_prereq_raw = blocks[i+2][4].strip()
                lines = ch_prereq_raw.split('\n')
                if len(lines) >= 2:
                    ch = lines[0].strip()
                    prereqs = lines[1].strip()
                else:
                    # Sometimes they might be on one line separated by space
                    match = re.match(r"(.*? \(\d+\))\s+(.*)", ch_prereq_raw)
                    if match:
                        ch = match.group(1).strip()
                        prereqs = match.group(2).strip()
                    else:
                        ch = ch_prereq_raw
                        prereqs = "-"
                i += 3
                
            disciplines[course_id] = {
                "name": name,
                "ch": ch,
                "prereqs_raw": prereqs,
                "prereq_names": []
            }
        else:
            i += 1
            
    return disciplines

def process_pdf(pdf_path: Path):
    doc = fitz.open(str(pdf_path))
    blocks = doc[0].get_text("blocks")
    doc.close()
    
    disciplines = parse_blocks(blocks)
    
    # Second pass: resolve dependencies to names
    for course_id, data in disciplines.items():
        raw_p = data["prereqs_raw"]
        if raw_p == "-" or not raw_p:
            data["prereq_names"] = []
            continue
            
        # Parse comma separated or space separated IDs (e.g., "12,14" or "21, 23")
        # Removing any spaces around commas
        raw_p = raw_p.replace(" ", "")
        p_ids = raw_p.split(",")
        
        resolved = []
        for pid in p_ids:
            if pid in disciplines:
                resolved.append(f"[{pid}] {disciplines[pid]['name']}")
            else:
                resolved.append(f"[{pid}] (Desconhecido)")
        
        data["prereq_names"] = resolved
        
    return disciplines

def generate_markdown(disciplines: dict) -> str:
    lines = [
        "---",
        'title: "Fluxograma Curricular - Dependências e Pré-requisitos"',
        'curriculum: "Currículo 5 - Criado em 2019"',
        f'total_disciplinas: {len(disciplines)}',
        f'extracted_at: "{datetime.now().isoformat(timespec="seconds")}"',
        "---",
        "",
        "# Grade Curricular (Fluxograma)",
        ""
    ]
    
    # Sort by ID
    for course_id in sorted(disciplines.keys()):
        data = disciplines[course_id]
        lines.append(f"## [{course_id}] {data['name']}")
        lines.append(f"- **Carga Horária (Créditos):** {data['ch']}")
        
        if data["prereq_names"]:
            lines.append("- **Pré-requisitos:**")
            for req in data["prereq_names"]:
                lines.append(f"  - {req}")
        else:
            lines.append("- **Pré-requisitos:** Nenhum")
            
        lines.append("")
        
    return "\n".join(lines)

def generate_txt(disciplines: dict) -> str:
    lines = [
        "================================================================================",
        " FLUXOGRAMA CURRICULAR - DEPENDÊNCIAS E PRÉ-REQUISITOS",
        " Currículo 5 - Criado em 2019",
        f" Total de disciplinas: {len(disciplines)}",
        "================================================================================",
        ""
    ]
    
    for course_id in sorted(disciplines.keys()):
        data = disciplines[course_id]
        lines.append(f"[{course_id}] {data['name'].upper()}")
        lines.append(f"Carga Horária: {data['ch']}")
        
        if data["prereq_names"]:
            lines.append("Pré-requisitos:")
            for req in data["prereq_names"]:
                lines.append(f"  -> {req}")
        else:
            lines.append("Pré-requisitos: NENHUM")
            
        lines.append("-" * 80)
        
    return "\n".join(lines)

def main():
    if not INPUT_PDF.exists():
        print(f"[ERRO] PDF não encontrado: {INPUT_PDF}")
        return
        
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    
    print(f"Processando fluxograma: {INPUT_PDF.name}")
    disciplines = process_pdf(INPUT_PDF)
    
    print(f"Extração concluída: {len(disciplines)} caixas processadas.")
    
    md_path = OUTPUT_DIR / "fluxograma_2019.md"
    txt_path = OUTPUT_DIR / "fluxograma_2019.txt"
    
    md_path.write_text(generate_markdown(disciplines), encoding="utf-8")
    txt_path.write_text(generate_txt(disciplines), encoding="utf-8")
    
    print(f"Arquivos gerados:")
    print(f"  - {md_path}")
    print(f"  - {txt_path}")

if __name__ == "__main__":
    main()
