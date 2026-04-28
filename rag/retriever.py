import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from langchain_chroma import Chroma
from rag.ingest import get_embeddings, slugify_model
from config.settings import config


def get_retriever(k: int = 4):
    embeddings = get_embeddings()
    fmt = config.experiment.format
    model_slug = slugify_model(config.embeddings.model_name)

    # Must match the path built in ingest.py:
    # chroma_db/<modelslug>_db_<fmt>
    db_path = str(
        PROJECT_ROOT / config.experiment.chroma_db_dir / f"{model_slug}_db_{fmt}"
    )

    print(f"[*] Loading ChromaDB from {db_path}...")
    vectorstore = Chroma(
        persist_directory=db_path,
        embedding_function=embeddings,
    )

    return vectorstore.as_retriever(search_kwargs={"k": k})
