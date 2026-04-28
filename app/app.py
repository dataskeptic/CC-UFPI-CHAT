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
    initial_sidebar_state="collapsed",
)

# ── CSS ───────────────────────────────────────────────────────────────────────

st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Instrument+Serif:ital@0;1&family=DM+Sans:opsz,wght@9..40,300;9..40,400;9..40,500&family=JetBrains+Mono:wght@400;500&display=swap');

/* ── Full-page warm grid — covers everything including stBottom area ── */
html {
    background-color: #EDEAE3 !important;
    background-image:
        linear-gradient(rgba(90,80,60,0.09) 1px, transparent 1px),
        linear-gradient(90deg, rgba(90,80,60,0.09) 1px, transparent 1px) !important;
    background-size: 40px 40px !important;
    background-attachment: fixed !important;
}
body {
    background: transparent !important;
}
.stApp {
    background: transparent !important;
    min-height: 100vh;
}

/* stBottom: fully transparent so the html background shows through */
[data-testid="stBottom"],
[data-testid="stBottom"] > div,
[data-testid="stBottom"] > div > div {
    background: transparent !important;
    border: none !important;
    box-shadow: none !important;
}

/* ── Global text color ── */
html, body,
[class*="css"],
.stMarkdown, .stMarkdown p, .stMarkdown li,
.stMarkdown strong, .stMarkdown b, .stMarkdown em,
[data-testid="stMarkdownContainer"],
[data-testid="stMarkdownContainer"] *,
p, span, li, td, th, label {
    font-family: 'DM Sans', sans-serif !important;
    color: #1A1816 !important;
}

/* ── Hide chrome ── */
#MainMenu, header, footer,
[data-testid="collapsedControl"],
[data-testid="stToolbar"],
[data-testid="stDecoration"] { display: none !important; }

/* ── Layout ── */
.block-container {
    max-width: 760px !important;
    padding: 3.5rem 2rem 1rem !important;
}

/* ── Badge ── */
.badge-wrap {
    display: flex;
    justify-content: center;
    margin-bottom: 2.4rem;
}
.badge {
    display: inline-flex;
    align-items: center;
    border: 1px solid #C4BFB5;
    border-radius: 999px;
    background: #F4F1EA;
    overflow: hidden;
    font-size: 0.76rem;
    box-shadow: 0 1px 4px rgba(0,0,0,0.08);
}
.badge-label {
    padding: 0.3rem 0.9rem;
    color: #6B6459 !important;
    font-weight: 400;
}
.badge-cta {
    padding: 0.3rem 0.9rem;
    background: #1A1816;
    color: #F4F1EA !important;
    font-weight: 500;
    border-radius: 999px;
    margin: 3px;
}

/* ── Hero ── */
.hero { text-align: center; margin-bottom: 0.8rem; }
.hero h1 {
    font-family: 'Instrument Serif', Georgia, serif !important;
    font-size: clamp(2.8rem, 6vw, 5rem);
    font-weight: 400;
    line-height: 1.1;
    color: #1A1816 !important;
    margin: 0 0 1.1rem;
    letter-spacing: -0.01em;
}
.hero h1 em {
    font-style: italic;
    color: #3D3830 !important;
}
.hero .sub {
    font-size: 0.93rem;
    color: #857E74 !important;
    line-height: 1.7;
    max-width: 500px;
    margin: 0 auto 2rem;
    font-weight: 300;
}

/* ── TERMINAL chat input ── */
/* Outer shell */
[data-testid="stChatInput"] {
    background: #13110C !important;
    border: 1px solid #2A2520 !important;
    border-radius: 12px !important;
    padding: 0 !important;
    overflow: hidden !important;
    box-shadow: 0 8px 48px rgba(0,0,0,0.5), 0 2px 10px rgba(0,0,0,0.3) !important;
}
/* macOS dots title bar via ::before */
[data-testid="stChatInput"]::before {
    content: '●  ●  ●';
    display: block;
    background: #1C1A14;
    color: #3A3530;
    font-size: 0.65rem;
    letter-spacing: 5px;
    padding: 0.5rem 1rem 0.4rem;
    border-bottom: 1px solid #252118;
    pointer-events: none;
}
/* Nuke ALL inner backgrounds — Streamlit nests many divs */
[data-testid="stChatInput"] *:not(textarea):not(button):not(svg):not(path) {
    background: transparent !important;
    border: none !important;
    box-shadow: none !important;
    outline: none !important;
}
/* The actual textarea */
[data-testid="stChatInput"] textarea {
    background: #13110C !important;
    color: #3EC97A !important;
    font-family: 'JetBrains Mono', 'Fira Mono', monospace !important;
    font-size: 0.87rem !important;
    line-height: 1.65 !important;
    border: none !important;
    box-shadow: none !important;
    outline: none !important;
    caret-color: #3EC97A !important;
    padding: 0.85rem 1rem !important;
    resize: none !important;
}
[data-testid="stChatInput"] textarea::placeholder {
    color: #2E3A2E !important;
    font-family: 'JetBrains Mono', monospace !important;
}
/* Send button */
[data-testid="stChatInput"] button {
    background: #1C1A14 !important;
    border: 1px solid #2A2520 !important;
    border-radius: 6px !important;
    color: #3EC97A !important;
    margin: 0 0.5rem 0.5rem 0 !important;
}
[data-testid="stChatInput"] button:hover {
    background: #252118 !important;
    color: #6EDEA0 !important;
}
[data-testid="stChatInput"] button svg,
[data-testid="stChatInput"] button svg path {
    fill: #3EC97A !important;
    stroke: #3EC97A !important;
    color: #3EC97A !important;
}

/* ── Suggestion tags ── */
.tags-wrap {
    display: flex;
    justify-content: center;
    flex-wrap: wrap;
    gap: 0.45rem;
    margin-top: 1rem;
    margin-bottom: 0.5rem;
}
.tag {
    font-size: 0.75rem;
    color: #5A5650 !important;
    padding: 0.35rem 0.85rem;
    border: 1px solid #C0BAB0;
    border-radius: 5px;
    background: rgba(244,241,234,0.8);
    cursor: default;
    font-family: 'DM Sans', sans-serif !important;
}

/* ── Chat messages ── */
[data-testid="stChatMessage"] {
    background: rgba(248,245,238,0.75) !important;
    border: 1px solid #D5D0C8 !important;
    border-radius: 12px !important;
    margin-bottom: 0.6rem !important;
}
[data-testid="stChatMessage"] p,
[data-testid="stChatMessage"] li,
[data-testid="stChatMessage"] span,
[data-testid="stChatMessage"] strong,
[data-testid="stChatMessage"] b,
[data-testid="stChatMessage"] em,
[data-testid="stChatMessage"] code {
    color: #1A1816 !important;
    font-size: 0.91rem !important;
    line-height: 1.75 !important;
}
[data-testid="stChatMessage"]:has([data-testid="chatAvatarIcon-assistant"]) {
    background: rgba(255,253,247,0.9) !important;
}

/* ── Expander (sources) ── */
[data-testid="stExpander"] {
    background: rgba(244,241,234,0.6) !important;
    border: 1px solid #D5D0C8 !important;
    border-radius: 10px !important;
}
[data-testid="stExpander"] summary,
[data-testid="stExpander"] summary p,
[data-testid="stExpander"] summary span { color: #7A7268 !important; font-size: 0.78rem !important; }
[data-testid="stExpander"] p,
[data-testid="stExpander"] span { color: #2A2720 !important; }

/* ── Clear button ── */
[data-testid="stButton"] button {
    background: transparent !important;
    border: 1px solid #C0BAB0 !important;
    color: #7A7268 !important;
    font-size: 0.78rem !important;
    border-radius: 8px !important;
}
[data-testid="stButton"] button:hover {
    background: rgba(0,0,0,0.04) !important;
    color: #2A2720 !important;
}

/* ── Spinner ── */
[data-testid="stSpinner"] p { color: #7A7268 !important; }

/* ── Divider ── */
hr { border-color: #D5D0C8 !important; opacity: 1 !important; }
</style>
""", unsafe_allow_html=True)

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
    com base nos documentos oficiais da UFPI — PPC, Regulamento, Fluxograma,
    Calendário e Corpo Docente.
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

if prompt := st.chat_input("▸  pergunte sobre disciplinas, professores, calendário..."):
    if not os.environ.get("OPENROUTER_API_KEY"):
        st.error("OPENROUTER_API_KEY não encontrada. Adicione ao arquivo .env.")
        st.stop()

    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    with st.chat_message("assistant"):
        with st.spinner("consultando documentos..."):
            try:
                result = ask(prompt)
                answer, sources = result["answer"], result["sources"]
            except Exception as e:
                answer, sources = f"Erro: {e}", []
        st.markdown(answer)

    st.session_state.messages.append({"role": "assistant", "content": answer})
    st.session_state.sources_history.append(sources)
    st.rerun()

# ── Suggestion tags (empty state only) ───────────────────────────────────────

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
        if st.button("limpar conversa", use_container_width=True):
            st.session_state.messages = []
            st.session_state.sources_history = []
            st.rerun()
