#!/usr/bin/env python3
"""
app.py — Streamlit chat interface for CC-UFPI-CHAT.

Run from the repo root:
    PYTHONPATH=rag streamlit run app.py
"""

import sys
import os
from pathlib import Path

# ── Load .env before anything else ────────────────────────────────────────────
# Looks for .env in the project root (same folder as this file).
# Variables already set in the environment take priority (override=False).
try:
    from dotenv import load_dotenv
    load_dotenv(dotenv_path=Path(__file__).parent / ".env", override=True)
except ImportError:
    pass  # python-dotenv not installed; rely on shell environment

# ── Make rag/ importable when running from repo root ──────────────────────────
RAG_DIR = os.path.join(os.path.dirname(__file__), "rag")
if RAG_DIR not in sys.path:
    sys.path.insert(0, RAG_DIR)

import streamlit as st
from pipeline import ask

# ── Page config ───────────────────────────────────────────────────────────────

st.set_page_config(
    page_title="CC-UFPI Chat",
    page_icon="🎓",
    layout="wide",
)

# ── Custom CSS ────────────────────────────────────────────────────────────────

st.markdown("""
<style>
.source-card {
    background: #f8f9fa;
    border-left: 4px solid #0068c9;
    border-radius: 6px;
    padding: 10px 14px;
    margin-bottom: 8px;
    font-size: 0.85rem;
}
.source-label {
    font-weight: 600;
    color: #0068c9;
    margin-bottom: 4px;
}
.source-snippet {
    color: #444;
    line-height: 1.5;
}
</style>
""", unsafe_allow_html=True)

# ── Sidebar ───────────────────────────────────────────────────────────────────

with st.sidebar:
    st.image("https://www.ufpi.br/images/logo_ufpi.png", width=160)
    st.title("CC-UFPI Chat")
    st.markdown(
        "Assistente acadêmico do curso de **Ciência da Computação — UFPI**.\n\n"
        "Faça perguntas sobre:\n"
        "- 📘 Projeto Pedagógico do Curso (PPC)\n"
        "- 📋 Regulamento de Graduação\n"
        "- 🗺️ Fluxograma Curricular"
    )
    st.divider()

    # If key is already loaded from .env, show a success indicator.
    # Otherwise show the manual input as fallback.
    if os.environ.get("OPENROUTER_API_KEY"):
        st.success("🔑 API Key carregada do ambiente.", icon="✅")
        # Still allow override via input if user wants to swap keys
        api_key_override = st.text_input(
            "Substituir API Key (opcional)",
            type="password",
            placeholder="sk-or-...",
            help="Deixe em branco para usar a chave do arquivo .env.",
        )
        if api_key_override:
            os.environ["OPENROUTER_API_KEY"] = api_key_override
    else:
        st.warning("⚠️ Nenhuma API Key encontrada no ambiente.")
        api_key_input = st.text_input(
            "🔑 OpenRouter API Key",
            type="password",
            placeholder="sk-or-...",
            help="Ou adicione OPENROUTER_API_KEY ao arquivo .env na raiz do projeto.",
        )
        if api_key_input:
            os.environ["OPENROUTER_API_KEY"] = api_key_input

    st.divider()
    if st.button("🗑️ Limpar conversa"):
        st.session_state.messages = []
        st.session_state.sources_history = []
        st.rerun()

    st.caption("CC-UFPI-CHAT · Monografia UFPI")

# ── Session state ─────────────────────────────────────────────────────────────

if "messages" not in st.session_state:
    st.session_state.messages = []

if "sources_history" not in st.session_state:
    st.session_state.sources_history = []

# ── Main layout: chat (left) + sources (right) ────────────────────────────────

col_chat, col_sources = st.columns([2, 1])

with col_chat:
    st.subheader("💬 Conversa")

    for msg in st.session_state.messages:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])

    user_input = st.chat_input("Faça uma pergunta sobre o curso...")

    if user_input:
        if not os.environ.get("OPENROUTER_API_KEY"):
            st.warning("⚠️ Insira sua chave de API do OpenRouter na barra lateral ou adicione-a ao arquivo .env.")
            st.stop()

        st.session_state.messages.append({"role": "user", "content": user_input})
        with st.chat_message("user"):
            st.markdown(user_input)

        with st.chat_message("assistant"):
            with st.spinner("Buscando nos documentos..."):
                try:
                    result = ask(user_input)
                    answer = result["answer"]
                    sources = result["sources"]
                except EnvironmentError as e:
                    answer = f"❌ Erro de configuração: {e}"
                    sources = []
                except Exception as e:
                    answer = f"❌ Erro ao processar a pergunta: {e}"
                    sources = []

            st.markdown(answer)

        st.session_state.messages.append({"role": "assistant", "content": answer})
        st.session_state.sources_history.append(sources)

        st.rerun()

# ── Sources panel ─────────────────────────────────────────────────────────────

with col_sources:
    st.subheader("📄 Documentos Recuperados")

    if not st.session_state.sources_history:
        st.info("Os trechos dos documentos usados para gerar cada resposta aparecerão aqui.")
    else:
        latest_sources = st.session_state.sources_history[-1]

        if not latest_sources:
            st.warning("Nenhum documento foi recuperado para a última pergunta.")
        else:
            st.caption(f"**{len(latest_sources)} trechos** usados na última resposta:")

            for i, doc in enumerate(latest_sources, 1):
                source_file = doc.metadata.get("source", "desconhecido")
                section = doc.metadata.get("Section", "")

                if "fluxograma" in source_file.lower():
                    icon = "🗺️"
                elif "ppc" in source_file.lower():
                    icon = "📘"
                elif "regulamento" in source_file.lower():
                    icon = "📋"
                else:
                    icon = "📄"

                label = f"{icon} {source_file}"
                if section:
                    label += f" › {section}"

                with st.expander(f"Trecho {i} — {label}", expanded=(i == 1)):
                    st.markdown(doc.page_content)

        if len(st.session_state.sources_history) > 1:
            st.divider()
            st.caption("Histórico de fontes:")
            user_messages = [
                msg["content"]
                for msg in st.session_state.messages
                if msg["role"] == "user"
            ]
            options = [
                f"Pergunta {i+1}: {q[:50]}..."
                if len(q) > 50 else f"Pergunta {i+1}: {q}"
                for i, q in enumerate(user_messages)
            ]
            if options:
                selected_idx = st.selectbox(
                    "Ver fontes de:",
                    range(len(options)),
                    format_func=lambda i: options[i],
                    index=len(options) - 1,
                )
                selected_sources = st.session_state.sources_history[selected_idx]
                if selected_idx != len(options) - 1:
                    st.caption(f"**{len(selected_sources)} trechos** para a pergunta selecionada:")
                    for i, doc in enumerate(selected_sources, 1):
                        source_file = doc.metadata.get("source", "desconhecido")
                        section = doc.metadata.get("Section", "")
                        with st.expander(f"Trecho {i} — {source_file}", expanded=False):
                            st.markdown(doc.page_content)
