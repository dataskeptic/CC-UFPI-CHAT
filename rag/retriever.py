from langchain_community.vectorstores import Chroma
from ingest import get_embeddings
from config import config

def get_retriever():
    embeddings = get_embeddings()
    format = config.experiment.format
    db_path = f"./chroma_db_{format}"
    
    print(f"[*] Loading ChromaDB from {db_path}...")
    vectorstore = Chroma(
        persist_directory=db_path,
        embedding_function=embeddings
    )
    
    # We retrieve the top 4 most similar chunks
    return vectorstore.as_retriever(search_kwargs={"k": 4})

if __name__ == "__main__":
    retriever = get_retriever()
    query = "Quais são os pré-requisitos da disciplina de Computação Gráfica?"
    print(f"[*] Testing query: '{query}'")
    docs = retriever.invoke(query)
    
    print(f"\n[+] Encontrei {len(docs)} chunks:")
    for i, doc in enumerate(docs):
        print(f"\n--- Chunk {i+1} ---")
        print(f"Metadata: {doc.metadata}")
        print(doc.page_content[:300] + "...")
