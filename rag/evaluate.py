import os
import json
from datasets import Dataset
from ragas import evaluate
from ragas.metrics import context_precision, context_recall, faithfulness, answer_relevancy
from langchain_openai import ChatOpenAI
from langchain_core.prompts import PromptTemplate
from langchain_core.runnables import RunnablePassthrough
from langchain_core.output_parsers import StrOutputParser

from retriever import get_retriever
from config import config

def get_llm():
    if config.llm.provider == "openrouter":
        return ChatOpenAI(
            base_url="https://openrouter.ai/api/v1",
            api_key=os.environ.get("OPENROUTER_API_KEY", "dummy"),
            model=config.llm.model,
            temperature=config.llm.temperature
        )
    else:
        raise NotImplementedError("Only OpenRouter configured right now.")

def build_rag_chain(retriever, llm):
    prompt_template = """Você é um assistente acadêmico da UFPI. Use o seguinte contexto para responder à pergunta.
Se não souber a resposta baseada no contexto, diga que não sabe.

Contexto: {context}

Pergunta: {question}

Resposta:"""
    prompt = PromptTemplate.from_template(prompt_template)
    
    def format_docs(docs):
        return "\n\n".join(doc.page_content for doc in docs)
        
    rag_chain = (
        {"context": retriever | format_docs, "question": RunnablePassthrough()}
        | prompt
        | llm
        | StrOutputParser()
    )
    return rag_chain

def run_evaluation():
    print("[*] Loading eval dataset...")
    with open("eval_dataset.json", "r", encoding="utf-8") as f:
        data = json.load(f)
        
    retriever = get_retriever()
    llm = get_llm()
    rag_chain = build_rag_chain(retriever, llm)
    
    questions = []
    ground_truths = []
    answers = []
    contexts = []
    
    print("[*] Running RAG pipeline to generate answers for evaluation...")
    for item in data:
        q = item["question"]
        gt = item["ground_truth"]
        
        # Retrieve context
        docs = retriever.invoke(q)
        ctx = [doc.page_content for doc in docs]
        
        # We skip the actual LLM call if the user hasn't provided an API key to avoid errors in this test
        if os.environ.get("OPENROUTER_API_KEY") is None:
            ans = "Sem chave de API para gerar resposta real."
        else:
            ans = rag_chain.invoke(q)
            
        questions.append(q)
        ground_truths.append([gt]) # Ragas expects a list of ground truths per question
        contexts.append(ctx)
        answers.append(ans)
        
    # Prepare Ragas Dataset
    eval_data = {
        "question": questions,
        "answer": answers,
        "contexts": contexts,
        "ground_truth": ground_truths
    }
    dataset = Dataset.from_dict(eval_data)
    
    print("\n[*] Running RAGAS Evaluation...")
    print("    Format being tested:", config.experiment.format)
    # If no API key, faithfulness and answer_relevancy will fail, so we only measure retrieval
    metrics = [context_precision, context_recall]
    
    if os.environ.get("OPENROUTER_API_KEY"):
        metrics.extend([faithfulness, answer_relevancy])
        
    try:
        # Ragas requires an LLM to evaluate the metrics
        result = evaluate(
            dataset,
            metrics=metrics,
            llm=llm
        )
        print("\n=== RESULTS ===")
        print(result)
    except Exception as e:
        print("\n[!] Evaluation error. Make sure you set OPENROUTER_API_KEY.")
        print(e)

if __name__ == "__main__":
    run_evaluation()
