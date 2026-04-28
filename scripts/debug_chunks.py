#!/usr/bin/env python3
"""
debug_chunks.py

Runs every folder chunker from FOLDER_REGISTRY against the current config
(format + documents_dir) WITHOUT loading embeddings or touching ChromaDB.

Outputs:
  - Terminal summary: folder stats + first 3 chunks per folder
  - chunks_debug_<fmt>.json: full export of every chunk for deep inspection

Usage:
    python scripts/debug_chunks.py
    python scripts/debug_chunks.py --folder extracted_regulamento
    python scripts/debug_chunks.py --folder professors --preview 5
"""

import sys
import json
import argparse
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from config.settings import config
from rag.ingest import FOLDER_REGISTRY


def collect_chunks(fmt: str, docs_dir: Path, only_folder: str | None = None) -> dict:
    """
    Run all chunkers (or a single one) and return a dict:
        { folder_name: [chunks...] }
    """
    results = {}

    for folder_name, registry in FOLDER_REGISTRY.items():
        if only_folder and folder_name != only_folder:
            continue

        folder_path = docs_dir / folder_name
        if not folder_path.exists():
            print(f"[!] '{folder_name}' not found — skipping.")
            continue

        chunker = registry[fmt]

        if registry["subdir"]:
            sub = folder_path / fmt
            if not sub.exists():
                print(f"[!] '{folder_name}/{fmt}' subdir not found — skipping.")
                continue
            files = list(sub.glob(f"*.{fmt}"))
        else:
            files = list(folder_path.glob(f"*.{fmt}"))

        if not files:
            print(f"[!] '{folder_name}': no .{fmt} files found.")
            continue

        chunks = chunker(files)
        results[folder_name] = chunks

    return results


def print_summary(results: dict, preview: int = 3) -> None:
    total = sum(len(c) for c in results.values())
    print(f"\n{'='*65}")
    print(f"  CHUNK DEBUG SUMMARY")
    print(f"  format : {config.experiment.format}")
    print(f"  total  : {total} chunks across {len(results)} folder(s)")
    print(f"{'='*65}")

    for folder_name, chunks in results.items():
        lengths = [len(c.page_content) for c in chunks]
        print(f"\n▶ {folder_name}")
        print(f"  chunks : {len(chunks)}")
        print(f"  chars  : min={min(lengths)}  max={max(lengths)}  avg={sum(lengths)//len(lengths)}")

        # Warn about suspiciously small or large chunks
        tiny  = [i for i, l in enumerate(lengths) if l < 40]
        giant = [i for i, l in enumerate(lengths) if l > max(lengths) * 0.9 and l > 800]
        if tiny:
            print(f"  ⚠   {len(tiny)} tiny chunk(s) (< 40 chars) at index(es): {tiny[:5]}")
        if giant:
            print(f"  ⚠   {len(giant)} oversized chunk(s) near ceiling at index(es): {giant[:5]}")

        print(f"\n  --- First {min(preview, len(chunks))} chunk(s) ---")
        for i, chunk in enumerate(chunks[:preview]):
            print(f"\n  [{i}] metadata : {chunk.metadata}")
            print(f"       length   : {len(chunk.page_content)} chars")
            preview_text = chunk.page_content[:300].replace("\n", " ")
            print(f"       content  : {preview_text}{'...' if len(chunk.page_content) > 300 else ''}")


def export_json(results: dict, fmt: str) -> Path:
    out_path = PROJECT_ROOT / f"chunks_debug_{fmt}.json"
    export = []
    for folder_name, chunks in results.items():
        for i, chunk in enumerate(chunks):
            export.append({
                "index": i,
                "folder": folder_name,
                "length": len(chunk.page_content),
                "metadata": chunk.metadata,
                "content": chunk.page_content,
            })
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(export, f, ensure_ascii=False, indent=2)
    return out_path


def main():
    parser = argparse.ArgumentParser(description="Debug chunking without touching ChromaDB.")
    parser.add_argument("--folder", default=None, help="Only debug this folder (e.g. extracted_regulamento)")
    parser.add_argument("--preview", type=int, default=3, help="Number of chunks to preview per folder (default: 3)")
    args = parser.parse_args()

    fmt = config.experiment.format
    docs_dir = PROJECT_ROOT / config.experiment.documents_dir

    print(f"[*] Format      : .{fmt}")
    print(f"[*] Docs dir    : {docs_dir}")
    if args.folder:
        print(f"[*] Filter      : {args.folder} only")

    results = collect_chunks(fmt, docs_dir, only_folder=args.folder)

    if not results:
        print("[!] No chunks collected. Check your config.yaml and folder paths.")
        sys.exit(1)

    print_summary(results, preview=args.preview)

    out_path = export_json(results, fmt)
    total = sum(len(c) for c in results.values())
    print(f"\n[*] Exported {total} chunks → {out_path}")
    print("    Open in VS Code and press Ctrl+Shift+P → 'Format Document' for a collapsible JSON tree.")


if __name__ == "__main__":
    main()
