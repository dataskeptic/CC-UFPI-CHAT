#!/usr/bin/env python3
"""
pipeline.py — Core RAG pipeline for CC-UFPI-CHAT.

Provides:
- get_llm()         : instantiate the LLM from config
- build_rag_chain() : full retriever → prompt → LLM chain
- ask()             : single-call helper that returns answer + source docs
"""

import sys
import os
from pathlib import Path
PROJECT_ROOT = Path(__file__).parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
from langchain_openai import ChatOpenAI
from langchain_core.prompts import PromptTemplate
from langchain_core.runnables import RunnablePassthrough
from langchain_core.output_parsers import StrOutputParser
from langchain_core.documents import Document

from rag.retriever import get_retriever
from config.settings import config


# ── Prompt ────────────────────────────────────────────────────────────────────

PROMPT_TEMPLATE = """Você é um assistente acadêmico do curso de Ciência da Computação da UFPI.
Responda à pergunta do aluno de forma clara, objetiva e em português.
Baseie-se EXCLUSIVAMENTE no contexto fornecido abaixo.
Se o contexto não contiver a informação necessária, diga honestamente que não sabe.

Contexto:
{context}

Pergunta: {question}

Resposta:"""


# ── LLM factory ───────────────────────────────────────────────────────────────

def get_llm():
    """Instantiate the LLM defined in config.yaml."""
    if config.llm.provider == "openrouter":
        api_key = os.environ.get("OPENROUTER_API_KEY", "")
        if not api_key:
            raise EnvironmentError(
                "OPENROUTER_API_KEY environment variable is not set. "
                "Add it to your .env file or export it before running."
            )
        return ChatOpenAI(
            base_url="https://openrouter.ai/api/v1",
            api_key=api_key,
            model=config.llm.model,
            temperature=config.llm.temperature,
        )
    else:
        raise NotImplementedError(
            f"Provider '{config.llm.provider}' is not supported yet. "
            "Only 'openrouter' is currently implemented."
        )


# ── Chain builder ─────────────────────────────────────────────────────────────

def build_rag_chain(retriever, llm):
    """
    Build a LangChain LCEL chain:
        question → retriever → format docs → prompt → LLM → string

    Returns the chain. Note: this chain returns only the final string answer.
    To also get source documents, use ask() instead.
    """
    prompt = PromptTemplate.from_template(PROMPT_TEMPLATE)

    def format_docs(docs: list[Document]) -> str:
        return "\n\n".join(doc.page_content for doc in docs)

    chain = (
        {"context": retriever | format_docs, "question": RunnablePassthrough()}
        | prompt
        | llm
        | StrOutputParser()
    )
    return chain


# ── Main helper ───────────────────────────────────────────────────────────────

def ask(question: str) -> dict:
    """
    Run the full RAG pipeline for a given question.

    Returns a dict with:
        {
            "answer":  str,
            "sources": list[Document]   # the retrieved chunks
        }

    This two-step approach (retrieve first, then generate) lets the caller
    inspect which documents were actually used to produce the answer.
    """
    retriever = get_retriever()
    llm = get_llm()

    # Step 1: retrieve relevant chunks
    source_docs = retriever.invoke(question)

    # Step 2: build context string and run LLM
    prompt = PromptTemplate.from_template(PROMPT_TEMPLATE)
    context_str = "\n\n".join(doc.page_content for doc in source_docs)

    chain = prompt | llm | StrOutputParser()
    answer = chain.invoke({"context": context_str, "question": question})

    return {
        "answer": answer,
        "sources": source_docs,
    }


# ── CLI smoke-test ─────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import sys

    question = " ".join(sys.argv[1:]) if len(sys.argv) > 1 else \
        "Quais são os pré-requisitos da disciplina de Computação Gráfica?"

    print(f"\n[?] Pergunta: {question}\n")

    result = ask(question)

    print(f"[✓] Resposta:\n{result['answer']}\n")
    print(f"[📄] Fontes recuperadas ({len(result['sources'])}):\n")
    for i, doc in enumerate(result["sources"], 1):
        source = doc.metadata.get("source", "desconhecido")
        section = doc.metadata.get("Section", "")
        label = f"{source}" + (f" › {section}" if section else "")
        print(f"  [{i}] {label}")
        print(f"      {doc.page_content[:200].strip()}...\n")
