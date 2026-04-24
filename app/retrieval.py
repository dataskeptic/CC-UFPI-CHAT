#!/usr/bin/env python3
"""
retrieval_app.py — Retrieval-only interface for CC-UFPI-CHAT.

Shows retrieved document chunks without calling the LLM.
Useful for debugging and evaluating the retriever.

Run from the repo root:
    streamlit run app/retrieval_app.py --server.port 8502
"""

import sys
import os
from pathlib import Path

try:
    from dotenv import load_dotenv
    load_dotenv(dotenv_path=Path(__file__).parent.parent / ".env", override=True)
except ImportError:
    pass

PROJECT_ROOT = os.path.dirname(os.path.dirname(__file__))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

import streamlit as st
from rag.retriever import get_retriever

# ── Page config ───────────────────────────────────────────────────────────────

st.set_page_config(
    page_title="CC-UFPI Retrieval",
    page_icon="🔍",
    layout="wide",
    initial_sidebar_state="collapsed",
)

st.markdown("""<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');
html, body, [class*="css"] { font-family: 'Inter', sans-serif !important; }
#MainMenu, header, footer, [data-testid="collapsedControl"] { display: none !important; }
.block-container { max-width: 900px !important; padding: 1rem 2rem !important; }

.hero { text-align:center; padding:2.5rem 0 1.2rem; }
.hero h1 { font-size:2rem; font-weight:700; margin:0; }
.hero h1 em { font-style:normal; background:linear-gradient(135deg,#34D399,#6EE7B7);
  -webkit-background-clip:text; -webkit-text-fill-color:transparent; }
.hero p { color:#8B949E; font-size:.88rem; margin:.5rem 0 0; }

.chunk-card {
  background: #161B22; border: 1px solid #21262D; border-radius: 10px;
  padding: 1rem 1.2rem; margin-bottom: .75rem;
  border-left: 3px solid #34D399;
}
.chunk-meta {
  font-size: .75rem; color: #34D399; font-weight: 600;
  text-transform: uppercase; letter-spacing: .04em; margin-bottom: .5rem;
}
.chunk-text { font-size: .85rem; color: #C9D1D9; line-height: 1.65; }
</style>""", unsafe_allow_html=True)

# ── Header ────────────────────────────────────────────────────────────────────

st.markdown("""<div class="hero">
  <h1><em>CC-UFPI</em> Retrieval</h1>
  <p>Teste o retriever — veja quais trechos são retornados para cada consulta, sem chamar o LLM</p>
</div>""", unsafe_allow_html=True)

st.divider()

# ── Cache the retriever so it loads once ──────────────────────────────────────

@st.cache_resource(show_spinner="Carregando retriever...")
def load_retriever():
    return get_retriever()

retriever = load_retriever()

# ── Query input ───────────────────────────────────────────────────────────────

query = st.text_input(
    "Consulta",
    placeholder="Ex: Quais os pré-requisitos de Computação Gráfica?",
    label_visibility="collapsed",
)

if query:
    with st.spinner("Buscando documentos..."):
        docs = retriever.invoke(query)

    st.markdown(f"**{len(docs)} trechos recuperados**")
    st.divider()

    for i, doc in enumerate(docs, 1):
        source = doc.metadata.get("source", "—")
        section = doc.metadata.get("Section", "")
        label = source + (f"  /  {section}" if section else "")

        st.markdown(
            f'<div class="chunk-card">'
            f'  <div class="chunk-meta">[{i}] {label}</div>'
            f'  <div class="chunk-text">{doc.page_content}</div>'
            f'</div>',
            unsafe_allow_html=True,
        )
