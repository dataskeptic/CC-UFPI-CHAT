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
    layout="centered",
    initial_sidebar_bar="collapsed",
)

# ── CSS ───────────────────────────────────────────────────────────────────────

st.markdown("""<style>
/* ── Fonts ── */
@import url('https://fonts.googleapis.com/css2?family=Instrument+Serif:ital@0;1&family=DM+Sans:wght@300;400;500&display=swap');

/* ── Global reset ── */
html, body, [class*="css"] {
    font-family: 'DM Sans', sans-serif !important;
    font-size: 15px;
}

/* ── Warm grid background ── */
.stApp {
    background-color: #EDEAE3 !important;
    background-image:
        linear-gradient(rgba(100,90,70,0.10) 1px, transparent 1px),
        linear-gradient(90deg, rgba(100,90,70,0.10) 1px, transparent 1px) !important;
    background-size: 40px 40px !important;
}

/* ── Hide Streamlit chrome ── */
#MainMenu, header, footer,
[data-testid="collapsedControl"],
[data-testid="stToolbar"] { display: none !important; }

/* ── Content width ── */
.block-container {
    max-width: 760px !important;
    padding: 3.5rem 2rem 2rem !important;
}

/* ── Badge ── */
.badge-wrap {
    display: flex;
    justify-content: center;
    margin-bottom: 2.2rem;
}
.badge {
    display: inline-flex;
    align-items: center;
    gap: 0;
    border: 1px solid #C8C3B8;
    border-radius: 999px;
    background: #F5F2EB;
    overflow: hidden;
    font-size: 0.78rem;
    box-shadow: 0 1px 3px rgba(0,0,0,0.07);
}
.badge-label {
    padding: 0.28rem 0.85rem;
    color: #6B6459;
    font-family: 'DM Sans', sans-serif;
    font-weight: 400;
}
.badge-cta {
    padding: 0.28rem 0.85rem;
    background: #1A1816;
    color: #F5F2EB;
    font-family: 'DM Sans', sans-serif;
    font-weight: 500;
    border-radius: 999px;
    margin: 2px;
}

/* ── Hero headline ── */
.hero {
    text-align: center;
    margin-bottom: 1rem;
}
.hero h1 {
    font-family: 'Instrument Serif', Georgia, serif !important;
    font-size: clamp(2.8rem, 6vw, 5rem);
    font-weight: 400;
    line-height: 1.1;
    color: #1A1816;
    margin: 0 0 1rem;
    letter-spacing: -0.01em;
}
.hero h1 em {
    font-style: italic;
    color: #3D3830;
}
.hero .sub {
    font-family: 'DM Sans', sans-serif;
    font-size: 0.95rem;
    color: #8A8278;
    line-height: 1.65;
    max-width: 520px;
    margin: 0 auto 2rem;
    font-weight: 300;
}

/* ── Dark terminal chat area ── */
.terminal-wrap {
    background: #16140F;
    border-radius: 16px;
    padding: 1.2rem 1.4rem 1rem;
    box-shadow: 0 8px 32px rgba(0,0,0,0.28), 0 2px 8px rgba(0,0,0,0.18);
    margin-bottom: 1.4rem;
    min-height: 100px;
    position: relative;
}
/* Give Streamlit's native chat input the terminal look */
[data-testid="stChatInput"] {
    background: #16140F !important;
    border-radius: 14px !important;
    border: 1px solid #2E2A22 !important;
    padding: 0.2rem !important;
    box-shadow: 0 8px 32px rgba(0,0,0,0.28) !important;
}
[data-testid="stChatInput"] textarea {
    background: transparent !important;
    color: #C8C3B4 !important;
    font-family: 'DM Sans', sans-serif !important;
    font-size: 0.95rem !important;
    border: none !important;
    caret-color: #4A9EFF !important;
}
[data-testid="stChatInput"] textarea::placeholder {
    color: #4A4640 !important;
}
[data-testid="stChatInput"] > div {
    border: none !important;
    background: transparent !important;
}
/* send button */
[data-testid="stChatInput"] button {
    background: #2A2720 !important;
    border-radius: 8px !important;
    color: #8A8278 !important;
}
[data-testid="stChatInput"] button:hover {
    background: #3A3530 !important;
    color: #C8C3B4 !important;
}

/* ── Suggestion tags ── */
.tags-wrap {
    display: flex;
    justify-content: center;
    flex-wrap: wrap;
    gap: 0.5rem;
    margin-top: 0.2rem;
}
.tag {
    font-size: 0.78rem;
    font-family: 'DM Sans', sans-serif;
    font-weight: 400;
    color: #5A5650;
    padding: 0.38rem 0.9rem;
    border: 1px solid #C0BBB0;
    border-radius: 6px;
    background: rgba(245,242,235,0.7);
    cursor: default;
}

/* ── Chat messages ── */
[data-testid="stChatMessage"] {
    background: rgba(245,242,235,0.6) !important;
    border: 1px solid #D8D3CB !important;
    border-radius: 12px !important;
    margin-bottom: 0.7rem !important;
    backdrop-filter: blur(4px);
}
[data-testid="stChatMessage"] p {
    color: #2A2720 !important;
    font-size: 0.92rem !important;
    line-height: 1.7 !important;
}
/* assistant bubble slight tint */
[data-testid="stChatMessage"]:has([data-testid="chatAvatarIcon-assistant"]) {
    background: rgba(255,252,245,0.85) !important;
}

/* ── Expander (sources) ── */
[data-testid="stExpander"] {
    background: rgba(245,242,235,0.5) !important;
    border: 1px solid #D8D3CB !important;
    border-radius: 10px !important;
}
[data-testid="stExpander"] summary {
    font-size: 0.8rem !important;
    color: #7A7268 !important;
    font-family: 'DM Sans', sans-serif !important;
}

/* ── Clear button ── */
[data-testid="stButton"] button {
    background: transparent !important;
    border: 1px solid #C0BBB0 !important;
    color: #7A7268 !important;
    font-family: 'DM Sans', sans-serif !important;
    font-size: 0.8rem !important;
    border-radius: 8px !important;
    padding: 0.4rem 1.2rem !important;
}
[data-testid="stButton"] button:hover {
    background: rgba(0,0,0,0.04) !important;
    color: #3A3530 !important;
}

/* ── Divider ── */
hr { border-color: #D8D3CB !important; }
</style>""", unsafe_allow_html=True)

# ── Badge + Hero ──────────────────────────────────────────────────────────────

st.markdown("""
<div class="badge-wrap">
  <div class="badge">
    <span class="badge-label">Assistente Oficial do CC-UFPI</span>
    <span class="badge-cta">Pergunte agora →</span>
  </div>
</div>

<div class="hero">
  <h1>Converse com os documentos<br><em>do seu curso.</em></h1>
  <p class="sub">
    O CC-UFPI Chat responde dúvidas sobre o curso de Ciência da Computação
    com base nos documentos oficiais da UFPI — sem enrolação, só informação.
  </p>
</div>
""", unsafe_allow_html=True)

# ── Session state ─────────────────────────────────────────────────────────────

if "messages" not in st.session_state:
    st.session_state.messages = []
if "sources_history" not in st.session_state:
    st.session_state.sources_history = []

# ── Render chat history ───────────────────────────────────────────────────────

for idx, msg in enumerate(st.session_state.messages):
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])

    if msg["role"] == "assistant":
        assistant_idx = sum(
            1 for m in st.session_state.messages[:idx + 1] if m["role"] == "assistant"
        ) - 1
        if assistant_idx < len(st.session_state.sources_history):
            sources = st.session_state.sources_history[assistant_idx]
            if sources:
                with st.expander(f"Fontes consultadas — {len(sources)} trecho(s)"):
                    for i, doc in enumerate(sources, 1):
                        src = doc.metadata.get("source", "—")
                        sec = doc.metadata.get("Section", "")
                        label = src + (f" / {sec}" if sec else "")
                        st.caption(f"**[{i}]** {label}")
                        st.markdown(doc.page_content)
                        if i < len(sources):
                            st.divider()

# ── Chat input ────────────────────────────────────────────────────────────────

if prompt := st.chat_input("Pergunte sobre disciplinas, professores, calendário..."):
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

# ── Suggestion tags (shown only when no conversation yet) ────────────────────

if not st.session_state.messages:
    st.markdown("""
<div class="tags-wrap">
  <span class="tag">PPC — Projeto Pedagógico</span>
  <span class="tag">Regulamento Acadêmico</span>
  <span class="tag">Fluxograma de Disciplinas</span>
  <span class="tag">Calendário Universitário</span>
  <span class="tag">Corpo Docente</span>
</div>
""", unsafe_allow_html=True)

# ── Clear button ──────────────────────────────────────────────────────────────

if st.session_state.messages:
    _, mid, _ = st.columns([2, 1, 2])
    with mid:
        if st.button("Limpar conversa", use_container_width=True):
            st.session_state.messages = []
            st.session_state.sources_history = []
            st.rerun()
