import os
import sys
import shutil
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from dotenv import load_dotenv
from langchain_community.document_loaders import TextLoader
from langchain_text_splitters import MarkdownHeaderTextSplitter, RecursiveCharacterTextSplitter
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_community.vectorstores import Chroma
from config.settings import config

# Load .env from project root (one level up from rag/)
load_dotenv(dotenv_path=PROJECT_ROOT / ".env", override=False)


def get_embeddings():
    hf_token = os.environ.get("HF_TOKEN")
    if not hf_token:
        raise EnvironmentError("HF_TOKEN not found. Add it to your .env file or export it in the shell.")

    if config.embeddings.type == "local":
        print(f"[*] Loading local HuggingFace model: {config.embeddings.model_name}")
        return HuggingFaceEmbeddings(
            model_name=config.embeddings.model_name,
            model_kwargs={
                'device': 'cpu',
                'token': hf_token,
            },
            encode_kwargs={'normalize_embeddings': True}
        )
    else:
        raise NotImplementedError("API embeddings not implemented yet")


# ── Format-specific chunking strategies ───────────────────────────────────────

def chunk_markdown(files: list[Path]) -> list:
    """
    Semantic chunking for .md files:
    1. Split by markdown headers (## and ###) to preserve document structure.
    2. Apply a secondary RecursiveCharacterTextSplitter for chunks that are
       still too large, ensuring nothing exceeds ~1500 chars.
    """
    headers_to_split_on = [
        ("##", "Section"),
        ("###", "Subsection"),
    ]
    md_splitter = MarkdownHeaderTextSplitter(
        headers_to_split_on=headers_to_split_on,
        strip_headers=False,
    )
    # Secondary splitter for oversized chunks
    secondary_splitter = RecursiveCharacterTextSplitter(
        chunk_size=1500,
        chunk_overlap=200,
        separators=["\n\n", "\n", ". ", " ", ""],
    )

    all_chunks = []
    for file in files:
        content = file.read_text(encoding="utf-8")
        header_chunks = md_splitter.split_text(content)

        for chunk in header_chunks:
            chunk.metadata["source"] = file.name
            # If the chunk is too large, split it further
            if len(chunk.page_content) > 1500:
                sub_chunks = secondary_splitter.create_documents(
                    [chunk.page_content],
                    metadatas=[chunk.metadata],
                )
                all_chunks.extend(sub_chunks)
            else:
                all_chunks.append(chunk)

    return all_chunks


def chunk_text(files: list[Path]) -> list:
    """
    Semantic chunking for .txt files:
    Uses custom separators that match the txt document structure:
    - '===...===' for major sections
    - '---...---' for subsections
    - '▸' for sub-headings
    - Standard paragraph breaks
    """
    text_splitter = RecursiveCharacterTextSplitter(
        chunk_size=1500,
        chunk_overlap=200,
        separators=[
            "\n================================================================================\n",
            "\n--------------------------------------------------------------------------------\n",
            "\n\n  ▸ ",
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
        chunks = text_splitter.split_documents(docs)
        all_chunks.extend(chunks)

    return all_chunks


# ── Main ingestion ────────────────────────────────────────────────────────────

def ingest_documents():
    docs_dir = PROJECT_ROOT / config.experiment.documents_dir
    fmt = config.experiment.format

    # Always use an absolute path anchored to PROJECT_ROOT
    db_path = str(PROJECT_ROOT / f"chroma_db_{fmt}")

    print(f"[*] Starting ingestion for format: .{fmt}")
    print(f"[*] Documents directory: {docs_dir}")
    print(f"[*] ChromaDB will be saved to: {db_path}")

    # 1. Clean stale DB to avoid mixing old and new data
    if os.path.exists(db_path):
        print(f"[*] Removing stale ChromaDB at {db_path}...")
        shutil.rmtree(db_path)

    # 2. Find all documents
    files = []
    for folder in ["extracted_regulamento", "extracted_ppc_cc", "extracted_fluxograma"]:
        folder_path = docs_dir / folder
        if folder_path.exists():
            found = list(folder_path.glob(f"*.{fmt}"))
            files.extend(found)
            print(f"    └─ {folder}: {len(found)} file(s)")

    print(f"[*] Found {len(files)} total files.")

    if not files:
        print("[!] No files found. Check documents_dir and format in config.yaml.")
        return

    # 3. Chunking — format-specific strategy
    if fmt == "md":
        all_chunks = chunk_markdown(files)
    else:
        all_chunks = chunk_text(files)

    print(f"[*] Generated {len(all_chunks)} chunks.")

    # 4. Embed & Store
    embeddings = get_embeddings()

    print(f"[*] Embedding and saving to ChromaDB at {db_path}...")
    vectorstore = Chroma.from_documents(
        documents=all_chunks,
        embedding=embeddings,
        persist_directory=db_path,
    )
    print(f"[*] Ingestion complete! {len(all_chunks)} chunks stored.")


if __name__ == "__main__":
    ingest_documents()