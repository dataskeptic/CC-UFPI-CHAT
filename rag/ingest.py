import os
from pathlib import Path
from langchain_community.document_loaders import TextLoader
from langchain_text_splitters import MarkdownHeaderTextSplitter, RecursiveCharacterTextSplitter
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_community.vectorstores import Chroma
from config import config

def get_embeddings():
    if config.embeddings.type == "local":
        print(f"[*] Loading local HuggingFace model: {config.embeddings.model_name}")
        return HuggingFaceEmbeddings(
            model_name=config.embeddings.model_name,
            model_kwargs={
                'device': 'cpu',
                'trust_remote_code': True,  # Required for models with custom code (e.g. Jina)
            },
            encode_kwargs={'normalize_embeddings': True}
        )
    else:
        raise NotImplementedError("API embeddings not implemented yet")

def ingest_documents():
    docs_dir = Path(config.experiment.documents_dir)
    format = config.experiment.format
    
    print(f"[*] Starting ingestion for format: .{format}")
    
    # 1. Find all documents
    files = []
    for folder in ["extracted_regulamento", "extracted_ppc_cc", "extracted_fluxograma"]:
        folder_path = docs_dir / folder
        if folder_path.exists():
            files.extend(list(folder_path.glob(f"*.{format}")))
            
    print(f"[*] Found {len(files)} files.")
    
    # 2. Chunking
    all_chunks = []
    
    if format == "md":
        headers_to_split_on = [
            ("##", "Section"),
        ]
        markdown_splitter = MarkdownHeaderTextSplitter(headers_to_split_on=headers_to_split_on)
        
        for file in files:
            content = file.read_text(encoding="utf-8")
            chunks = markdown_splitter.split_text(content)
            for chunk in chunks:
                chunk.metadata["source"] = file.name
            all_chunks.extend(chunks)
            
    else: # txt
        text_splitter = RecursiveCharacterTextSplitter(
            chunk_size=1000,
            chunk_overlap=100,
            separators=["\n\n[", "\n\n", "\n", " ", ""]
        )
        for file in files:
            loader = TextLoader(str(file), encoding="utf-8")
            docs = loader.load()
            chunks = text_splitter.split_documents(docs)
            all_chunks.extend(chunks)
            
    print(f"[*] Generated {len(all_chunks)} chunks.")
    
    # 3. Embed & Store
    embeddings = get_embeddings()
    db_path = f"./chroma_db_{format}"
    
    print(f"[*] Embedding and saving to ChromaDB at {db_path}...")
    vectorstore = Chroma.from_documents(
        documents=all_chunks,
        embedding=embeddings,
        persist_directory=db_path
    )
    print("[*] Ingestion Complete!")

if __name__ == "__main__":
    ingest_documents()
