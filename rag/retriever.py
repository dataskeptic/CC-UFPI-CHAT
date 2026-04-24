from pathlib import Path
from langchain_chroma import Chroma
from rag.ingest import get_embeddings
from config.settings import config


def get_retriever():
    embeddings = get_embeddings()
    format = config.experiment.format
    db_path = str(Path(__file__).parent / f"chroma_db_{format}")

    print(f"[*] Loading ChromaDB from {db_path}...")
    vectorstore = Chroma(
        persist_directory=db_path,
        embedding_function=embeddings
    )

    return vectorstore.as_retriever(search_kwargs={"k": 4})