import os
import re
import sys
import shutil
from pathlib import Path
from langchain_core.documents import Document

PROJECT_ROOT = Path(__file__).parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from dotenv import load_dotenv
from langchain_text_splitters import MarkdownHeaderTextSplitter, RecursiveCharacterTextSplitter
from config.settings import config

load_dotenv(dotenv_path=PROJECT_ROOT / ".env", override=False)


# ── Helpers ───────────────────────────────────────────────────────────────────

def slugify_model(model_name: str) -> str:
    """Turn 'google/embeddinggemma-300m' into 'embeddinggemma300m' for use in dir names."""
    name = model_name.split("/")[-1]
    name = re.sub(r"[^a-zA-Z0-9]", "", name)
    return name.lower()


def get_embeddings():
    """Lazy-loaded: heavy imports only happen when this function is called."""
    from langchain_huggingface import HuggingFaceEmbeddings  # noqa: PLC0415

    hf_token = os.environ.get("HF_TOKEN")
    if not hf_token:
        raise EnvironmentError("HF_TOKEN not found. Add it to your .env file or export it in the shell.")

    if config.embeddings.type == "local":
        print(f"[*] Loading local HuggingFace model: {config.embeddings.model_name}")
        return HuggingFaceEmbeddings(
            model_name=config.embeddings.model_name,
            model_kwargs={"device": "cpu", "token": hf_token},
            encode_kwargs={"normalize_embeddings": True},
        )
    raise NotImplementedError("API embeddings not implemented yet")


# ── Format-specific chunking strategies ───────────────────────────────────────

def _safety_splitter(chunk_size: int, chunk_overlap: int) -> RecursiveCharacterTextSplitter:
    return RecursiveCharacterTextSplitter(
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
        separators=["\n\n", "\n", ". ", " ", ""],
    )


def _apply_safety_split(chunks: list[Document], chunk_size: int, chunk_overlap: int) -> list[Document]:
    """Pass each chunk through the safety splitter only if it exceeds chunk_size."""
    splitter = _safety_splitter(chunk_size, chunk_overlap)
    result = []
    for chunk in chunks:
        if len(chunk.page_content) > chunk_size:
            result.extend(
                splitter.create_documents([chunk.page_content], metadatas=[chunk.metadata])
            )
        else:
            result.append(chunk)
    return result


# ── 1. extracted_regulamento ──────────────────────────────────────────────────

def chunk_regulamento_txt(files: list[Path]) -> list[Document]:
    art_pattern = re.compile(r"(?=\bArt\.\s*\d+)", re.IGNORECASE)
    all_chunks = []
    for file in files:
        text = file.read_text(encoding="utf-8")
        parts = art_pattern.split(text)
        for part in parts:
            part = part.strip()
            if not part:
                continue
            art_match = re.match(r"Art\.\s*(\d+)", part, re.IGNORECASE)
            metadata = {
                "source": file.name,
                "folder": "extracted_regulamento",
                "article": art_match.group(1) if art_match else None,
            }
            all_chunks.append(Document(page_content=part, metadata=metadata))
    return _apply_safety_split(all_chunks, chunk_size=1000, chunk_overlap=150)


def chunk_regulamento_md(files: list[Path]) -> list[Document]:
    headers_to_split_on = [("##", "Section"), ("###", "Subsection")]
    md_splitter = MarkdownHeaderTextSplitter(
        headers_to_split_on=headers_to_split_on, strip_headers=False
    )
    art_pattern = re.compile(r"(?=\bArt\.\s*\d+)", re.IGNORECASE)
    all_chunks = []
    for file in files:
        text = file.read_text(encoding="utf-8")
        header_chunks = md_splitter.split_text(text)
        for hchunk in header_chunks:
            hchunk.metadata["source"] = file.name
            hchunk.metadata["folder"] = "extracted_regulamento"
            parts = art_pattern.split(hchunk.page_content)
            for part in parts:
                part = part.strip()
                if not part:
                    continue
                art_match = re.match(r"Art\.\s*(\d+)", part, re.IGNORECASE)
                meta = dict(hchunk.metadata)
                meta["article"] = art_match.group(1) if art_match else None
                all_chunks.append(Document(page_content=part, metadata=meta))
    return _apply_safety_split(all_chunks, chunk_size=1000, chunk_overlap=150)


# ── 2. extracted_ppc_cc ───────────────────────────────────────────────────────

def chunk_ppc_txt(files: list[Path]) -> list[Document]:
    from langchain_community.document_loaders import TextLoader  # noqa: PLC0415
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=1200,
        chunk_overlap=150,
        separators=[
            "\n================================================================================\n",
            "\n--------------------------------------------------------------------------------\n",
            "\n\n  \u25b8 ",
            "\n\n",
            "\n",
            ". ",
            " ",
            "",
        ],
    )
    all_chunks = []
    for file in files:
        loader = TextLoader(str(file), encoding="utf-8")
        docs = loader.load()
        for doc in docs:
            doc.metadata["folder"] = "extracted_ppc_cc"
        chunks = splitter.split_documents(docs)
        all_chunks.extend(chunks)
    return all_chunks


def chunk_ppc_md(files: list[Path]) -> list[Document]:
    headers_to_split_on = [("#", "Chapter"), ("##", "Section"), ("###", "Subsection")]
    md_splitter = MarkdownHeaderTextSplitter(
        headers_to_split_on=headers_to_split_on, strip_headers=False
    )
    all_chunks = []
    for file in files:
        text = file.read_text(encoding="utf-8")
        chunks = md_splitter.split_text(text)
        for chunk in chunks:
            chunk.metadata["source"] = file.name
            chunk.metadata["folder"] = "extracted_ppc_cc"
        all_chunks.extend(chunks)
    return _apply_safety_split(all_chunks, chunk_size=1200, chunk_overlap=150)


# ── 3. extracted_fluxograma ───────────────────────────────────────────────────

_SEMESTER_PATTERN = re.compile(
    r"(?=(?:\d+[°º]\.?\s*(?:Per[íi]odo|Semestre)|Per[íi]odo\s+\d+|Semestre\s+\d+))",
    re.IGNORECASE,
)


def chunk_fluxograma_txt(files: list[Path]) -> list[Document]:
    all_chunks = []
    for file in files:
        text = file.read_text(encoding="utf-8")
        parts = _SEMESTER_PATTERN.split(text)
        if len(parts) <= 1:
            parts = [p.strip() for p in text.split("\n\n") if p.strip()]
        for part in parts:
            part = part.strip()
            if not part:
                continue
            sem_match = re.search(r"(\d+)[°º]", part)
            metadata = {
                "source": file.name,
                "folder": "extracted_fluxograma",
                "semester": sem_match.group(1) if sem_match else None,
            }
            all_chunks.append(Document(page_content=part, metadata=metadata))
    return _apply_safety_split(all_chunks, chunk_size=500, chunk_overlap=50)


def chunk_fluxograma_md(files: list[Path]) -> list[Document]:
    headers_to_split_on = [("##", "Period"), ("###", "Semester")]
    md_splitter = MarkdownHeaderTextSplitter(
        headers_to_split_on=headers_to_split_on, strip_headers=False
    )
    all_chunks = []
    for file in files:
        text = file.read_text(encoding="utf-8")
        chunks = md_splitter.split_text(text)
        if not chunks:
            all_chunks.extend(chunk_fluxograma_txt([file]))
            continue
        for chunk in chunks:
            chunk.metadata["source"] = file.name
            chunk.metadata["folder"] = "extracted_fluxograma"
        all_chunks.extend(chunks)
    return _apply_safety_split(all_chunks, chunk_size=500, chunk_overlap=50)


# ── 4. calendars ──────────────────────────────────────────────────────────────

_MONTH_NAMES = (
    "JANEIRO|FEVEREIRO|MAR[ÇC]O|ABRIL|MAIO|JUNHO|"
    "JULHO|AGOSTO|SETEMBRO|OUTUBRO|NOVEMBRO|DEZEMBRO"
)
_CALENDAR_HEADER = re.compile(
    rf"(?=(?:{_MONTH_NAMES}|\d+[°º]\.?\s*(?:PER[IÍ]ODO|SEMESTRE)|PERÍODO\s+\d+))",
    re.IGNORECASE,
)


def chunk_calendars_txt(files: list[Path]) -> list[Document]:
    all_chunks = []
    for file in files:
        text = file.read_text(encoding="utf-8")
        parts = _CALENDAR_HEADER.split(text)
        if len(parts) <= 1:
            parts = [p.strip() for p in text.split("\n\n") if p.strip()]
        for part in parts:
            part = part.strip()
            if not part:
                continue
            metadata = {"source": file.name, "folder": "calendars"}
            all_chunks.append(Document(page_content=part, metadata=metadata))
    return _apply_safety_split(all_chunks, chunk_size=600, chunk_overlap=100)


def chunk_calendars_md(files: list[Path]) -> list[Document]:
    headers_to_split_on = [("#", "Year"), ("##", "Month"), ("###", "Period")]
    md_splitter = MarkdownHeaderTextSplitter(
        headers_to_split_on=headers_to_split_on, strip_headers=False
    )
    all_chunks = []
    for file in files:
        text = file.read_text(encoding="utf-8")
        chunks = md_splitter.split_text(text)
        if not chunks:
            all_chunks.extend(chunk_calendars_txt([file]))
            continue
        for chunk in chunks:
            chunk.metadata["source"] = file.name
            chunk.metadata["folder"] = "calendars"
        all_chunks.extend(chunks)
    return _apply_safety_split(all_chunks, chunk_size=600, chunk_overlap=100)


# ── 5. professors ─────────────────────────────────────────────────────────────

def chunk_professors(files: list[Path]) -> list[Document]:
    all_chunks = []
    for file in files:
        text = file.read_text(encoding="utf-8").strip()
        if not text:
            continue
        professor_name = file.stem.replace("_", " ").title()
        metadata = {
            "source": file.name,
            "folder": "professors",
            "professor": professor_name,
        }
        all_chunks.append(Document(page_content=text, metadata=metadata))
    return all_chunks


# ── Folder registry ───────────────────────────────────────────────────────────

FOLDER_REGISTRY = {
    "extracted_regulamento": {
        "txt": chunk_regulamento_txt,
        "md": chunk_regulamento_md,
        "subdir": False,
    },
    "extracted_ppc_cc": {
        "txt": chunk_ppc_txt,
        "md": chunk_ppc_md,
        "subdir": False,
    },
    "extracted_fluxograma": {
        "txt": chunk_fluxograma_txt,
        "md": chunk_fluxograma_md,
        "subdir": False,
    },
    "calendars": {
        "txt": chunk_calendars_txt,
        "md": chunk_calendars_md,
        "subdir": False,
    },
    "professors": {
        "txt": chunk_professors,
        "md": chunk_professors,
        "subdir": True,
    },
}


# ── Main ingestion ────────────────────────────────────────────────────────────

def ingest_documents():
    from langchain_community.vectorstores import Chroma  # noqa: PLC0415

    docs_dir = PROJECT_ROOT / config.experiment.documents_dir
    fmt = config.experiment.format
    model_slug = slugify_model(config.embeddings.model_name)

    db_path = str(
        PROJECT_ROOT / config.experiment.chroma_db_dir / f"{model_slug}_db_{fmt}"
    )

    print(f"[*] Starting ingestion | format=.{fmt} | model={config.embeddings.model_name}")
    print(f"[*] Documents dir : {docs_dir}")
    print(f"[*] ChromaDB path : {db_path}")

    if os.path.exists(db_path):
        print(f"[*] Removing stale ChromaDB at {db_path}...")
        shutil.rmtree(db_path)

    all_chunks = []

    for folder_name, registry in FOLDER_REGISTRY.items():
        folder_path = docs_dir / folder_name
        if not folder_path.exists():
            print(f"[!] Skipping '{folder_name}' — folder not found.")
            continue

        chunker = registry[fmt]

        if registry["subdir"]:
            sub = folder_path / fmt
            if not sub.exists():
                print(f"[!] Skipping '{folder_name}/{fmt}' — subdirectory not found.")
                continue
            files = list(sub.glob(f"*.{fmt}"))
        else:
            files = list(folder_path.glob(f"*.{fmt}"))

        if not files:
            print(f"    └─ {folder_name}: 0 file(s) — skipping.")
            continue

        chunks = chunker(files)
        print(f"    └─ {folder_name}: {len(files)} file(s) → {len(chunks)} chunk(s)")
        all_chunks.extend(chunks)

    print(f"[*] Total chunks: {len(all_chunks)}")

    if not all_chunks:
        print("[!] No chunks produced. Check documents_dir and format in config.yaml.")
        return

    embeddings = get_embeddings()
    print(f"[*] Embedding and saving to ChromaDB...")
    Chroma.from_documents(
        documents=all_chunks,
        embedding=embeddings,
        persist_directory=db_path,
    )
    print(f"[*] Done! {len(all_chunks)} chunks stored at {db_path}")


if __name__ == "__main__":
    ingest_documents()
