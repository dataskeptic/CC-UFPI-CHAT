#!/usr/bin/env python3
"""
app.py — Streamlit chat interface for CC-UFPI-CHAT.

Run from the repo root:
    streamlit run app/app.py
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
from rag.pipeline import ask

# ── Page config ───────────────────────────────────────────────────────────────

st.set_page_config(
    page_title="CC-UFPI Chat",
    page_icon="🎓",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# ── Minimal CSS — only what Streamlit can't do natively ───────────────────────

st.markdown("""<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');
html, body, [class*="css"] { font-family: 'Inter', sans-serif !important; }

/* hide chrome */
#MainMenu, header, footer, [data-testid="collapsedControl"] { display: none !important; }

/* widen the content area */
.block-container { max-width: 860px !important; padding: 1rem 2rem !important; }

/* header block */
.hero { text-align:center; padding:2.5rem 0 1.2rem; }
.hero h1 { font-size:2rem; font-weight:700; margin:0; }
.hero h1 em { font-style:normal; background:linear-gradient(135deg,#7C6AFF,#B196FF);
  -webkit-background-clip:text; -webkit-text-fill-color:transparent; }
.hero p { color:#8B949E; font-size:.88rem; margin:.5rem 0 0; }
.pills { display:flex; justify-content:center; gap:.45rem; margin-top:.9rem; flex-wrap:wrap; }
.pill { font-size:.72rem; font-weight:500; padding:.3rem .7rem; border-radius:999px;
  border:1px solid rgba(124,106,255,.3); color:#B196FF; background:rgba(124,106,255,.06); }

/* chat bubbles */
[data-testid="stChatMessage"] {
  border-radius:12px !important; border:1px solid #21262D !important;
  margin-bottom:.6rem !important;
}
</style>""", unsafe_allow_html=True)

# ── Header ────────────────────────────────────────────────────────────────────

st.markdown("""<div class="hero">
  <h1><em>CC-UFPI</em> Chat</h1>
  <p>Converse com os documentos oficiais do curso de Ciência da Computação</p>
  <div class="pills">
    <span class="pill">PPC</span>
    <span class="pill">Regulamento</span>
    <span class="pill">Fluxograma</span>
  </div>
</div>""", unsafe_allow_html=True)

st.divider()

# ── Session state ─────────────────────────────────────────────────────────────

if "messages" not in st.session_state:
    st.session_state.messages = []
if "sources_history" not in st.session_state:
    st.session_state.sources_history = []

# ── Render chat history (messages + inline sources) ───────────────────────────

for idx, msg in enumerate(st.session_state.messages):
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])

    # After each assistant message, show its sources inline
    if msg["role"] == "assistant":
        # Figure out which sources_history index this corresponds to
        assistant_idx = sum(
            1 for m in st.session_state.messages[:idx + 1] if m["role"] == "assistant"
        ) - 1
        if assistant_idx < len(st.session_state.sources_history):
            sources = st.session_state.sources_history[assistant_idx]
            if sources:
                with st.expander(f"Fontes consultadas  —  {len(sources)} trechos"):
                    for i, doc in enumerate(sources, 1):
                        src = doc.metadata.get("source", "—")
                        sec = doc.metadata.get("Section", "")
                        label = src + (f" / {sec}" if sec else "")
                        st.caption(f"**[{i}]** {label}")
                        st.markdown(doc.page_content)
                        if i < len(sources):
                            st.divider()

# ── Chat input ────────────────────────────────────────────────────────────────

if prompt := st.chat_input("Pergunte sobre o curso..."):
    if not os.environ.get("OPENROUTER_API_KEY"):
        st.error("OPENROUTER_API_KEY não encontrada. Adicione ao arquivo .env.")
        st.stop()

    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    with st.chat_message("assistant"):
        with st.spinner("Consultando documentos..."):
            try:
                result = ask(prompt)
                answer, sources = result["answer"], result["sources"]
            except Exception as e:
                answer, sources = f"Erro: {e}", []
        st.markdown(answer)

    st.session_state.messages.append({"role": "assistant", "content": answer})
    st.session_state.sources_history.append(sources)
    st.rerun()

# ── Clear button (only when there's history) ──────────────────────────────────

if st.session_state.messages:
    _, mid, _ = st.columns([2, 1, 2])
    with mid:
        if st.button("Limpar conversa", use_container_width=True):
            st.session_state.messages = []
            st.session_state.sources_history = []
            st.rerun()
