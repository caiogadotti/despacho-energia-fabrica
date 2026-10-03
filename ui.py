"""Identidade visual e componentes de texto compartilhados pelos painéis."""
from __future__ import annotations

import plotly.graph_objects as go
import plotly.io as pio
import streamlit as st

TEAL, AMB, DARK, RED, GRAY, BLUE, INK, MUTED = (
    "#0F766E", "#B45309", "#0B2E2B", "#B91C1C", "#94A3B8", "#1D4ED8", "#1E293B", "#475569")
AMB_VIVO = "#F59E0B"

CSS = f"""
<style>
@import url('https://fonts.googleapis.com/css2?family=Instrument+Serif&family=Inter:wght@400;500;600&family=JetBrains+Mono:wght@500&display=swap');
:root {{ --teal:{TEAL}; --dark:{DARK}; --amb:{AMB}; --ink:{INK}; --muted:{MUTED}; --line:#E2E8F0; --soft:#F1F7F6; }}
html, body, [class*="css"] {{ font-family: 'Inter', sans-serif; color: var(--ink); }}
h1, h2, h3 {{ font-family: 'Instrument Serif', serif !important; font-weight: 400 !important; letter-spacing: 0; }}
h3 {{ font-size: 1.9rem !important; margin-top: .4rem !important; }}
.block-container {{ padding-top: 2.2rem; max-width: 1240px; }}

.hero {{ background: var(--dark); color: #fff; padding: 26px 30px 22px; border-radius: 16px; margin-bottom: 14px; }}
.hero .k {{ color: #5EEAD4; font-size: .75rem; font-weight: 600; letter-spacing: .14em; text-transform: uppercase; }}
.hero h1 {{ color: #fff; margin: 4px 0 6px; font-size: 2.6rem !important; line-height: 1.05; }}
.hero p {{ color: #CBD5E1; font-size: 1.02rem; margin: 0; max-width: 70ch; line-height: 1.55; }}
.hero .chips {{ display: flex; flex-wrap: wrap; gap: 8px; margin-top: 16px; }}
.hero .chip {{ background: #ffffff14; border: 1px solid #ffffff26; border-radius: 999px; padding: 5px 12px; font-size: .82rem; color: #E2E8F0; }}
.hero .chip b {{ color: #FCD34D; font-weight: 600; font-variant-numeric: tabular-nums; margin-left: 2px; }}
.hero .autor {{ color: #94A3B8; font-size: .82rem; margin-top: 14px; }}

.eyebrow {{ color: var(--teal); font-weight: 600; letter-spacing: .12em; font-size: .74rem; text-transform: uppercase; margin: 6px 0 4px; }}
.lead {{ color: var(--muted); font-size: 1rem; line-height: 1.6; max-width: 78ch; margin-bottom: 10px; }}
.box {{ background: var(--soft); border: 1px solid #D5E8E5; color: var(--ink); border-radius: 12px; padding: 14px 18px; margin-bottom: 12px; line-height: 1.6; }}
.box b {{ color: var(--teal); }}
.hint {{ color: #44403C; font-size: .94rem; background: #FFFBEB; border: 1px solid #FDE68A; border-radius: 10px; padding: 10px 14px; margin: 8px 0 12px; line-height: 1.55; }}
.result {{ background: var(--dark); color: #E2E8F0; border-radius: 12px; padding: 16px 20px; margin-bottom: 12px; line-height: 1.55; }}
.result .num {{ font-family: 'Instrument Serif', serif; font-size: 2.3rem; color: #FCD34D; line-height: 1.1; font-variant-numeric: tabular-nums; }}
.result b {{ color: #fff; }}

div[data-testid="stMetric"] {{ background: #fff; border: 1px solid var(--line); border-radius: 12px; padding: 12px 16px; }}
div[data-testid="stMetricValue"] {{ font-variant-numeric: tabular-nums; font-weight: 600; }}
div[data-testid="stMetricLabel"] p {{ color: var(--muted); font-weight: 500; }}
.stTabs [data-baseweb="tab-list"] {{ gap: 2px; border-bottom: 1px solid var(--line); }}
.stTabs [data-baseweb="tab"] {{ font-size: .98rem; padding: 10px 14px; min-height: 44px; }}
div[data-testid="stExpander"] details {{ border-radius: 12px; border-color: var(--line); }}
div[data-testid="stExpander"] summary p {{ font-weight: 600; }}

.escopo {{ display: grid; grid-template-columns: repeat(3, 1fr); gap: 14px; }}
.escopo > div {{ background: #fff; border: 1px solid var(--line); border-radius: 12px; padding: 14px 16px; line-height: 1.55; font-size: .94rem; }}
.escopo h4 {{ font-family: 'Inter', sans-serif; font-size: .74rem; letter-spacing: .12em; text-transform: uppercase; margin: 0 0 8px; color: var(--teal); }}
.escopo ul {{ margin: 0; padding-left: 18px; }} .escopo li {{ margin-bottom: 4px; }}
.escopo .fora h4 {{ color: var(--amb); }}

.glossario {{ width: 100%; border-collapse: collapse; font-size: .93rem; }}
.glossario td {{ border-top: 1px solid var(--line); padding: 9px 10px; vertical-align: top; line-height: 1.5; }}
.glossario td:first-child {{ font-weight: 600; white-space: nowrap; color: var(--ink); width: 1%; }}
.glossario td:nth-child(2) {{ font-family: 'JetBrains Mono', monospace; font-size: .8rem; color: var(--teal); white-space: nowrap; width: 1%; }}
.glossario td:last-child {{ color: var(--muted); }}

section[data-testid="stSidebar"] h3 {{ font-size: 1.6rem !important; color: var(--teal); }}
section[data-testid="stSidebar"] .stMarkdown p {{ line-height: 1.55; }}
@media (max-width: 760px) {{
  .hero {{ padding: 20px 18px; }} .hero h1 {{ font-size: 2rem !important; }}
  .escopo {{ grid-template-columns: 1fr; }}
  .glossario td:nth-child(2) {{ display: none; }}
}}
@media (prefers-reduced-motion: reduce) {{ * {{ transition: none !important; animation: none !important; }} }}
</style>
"""


def _html(h: str):
    """st.markdown lê $...$ como LaTeX; em HTML de texto o cifrão vira entidade."""
    st.markdown(h.replace("$", "&#36;"), unsafe_allow_html=True)


def aplicar():
    st.markdown(CSS, unsafe_allow_html=True)
    tpl = go.layout.Template()
    tpl.layout = go.Layout(
        font=dict(family="Inter, sans-serif", color=INK, size=13),
        paper_bgcolor="#fff", plot_bgcolor="#fff",
        colorway=[TEAL, AMB_VIVO, BLUE, RED, "#7C3AED", DARK],
        xaxis=dict(gridcolor="#EEF2F6", zerolinecolor="#CBD5E1", linecolor="#CBD5E1", ticks="outside",
                   tickcolor="#CBD5E1", title=dict(font=dict(size=12, color=MUTED))),
        yaxis=dict(gridcolor="#EEF2F6", zerolinecolor="#CBD5E1", linecolor="#CBD5E1",
                   title=dict(font=dict(size=12, color=MUTED))),
        legend=dict(orientation="h", y=1.12, x=0, font=dict(size=12)),
        hoverlabel=dict(bgcolor="#fff", bordercolor="#CBD5E1", font=dict(family="Inter", size=12, color=INK)),
        margin=dict(l=10, r=10, t=36, b=10),
        separators=",.",
    )
    pio.templates["painel"] = tpl
    pio.templates.default = "painel"


def hero(kicker: str, titulo: str, texto: str, chips: list[tuple[str, str]], autor: str):
    c = "".join(f'<span class="chip">{rot} <b>{val}</b></span>' for rot, val in chips)
    _html(f'<div class="hero"><div class="k">{kicker}</div><h1>{titulo}</h1><p>{texto}</p>'
                f'<div class="chips">{c}</div><div class="autor">{autor}</div></div>')


def escopo(problema: str, dentro: list[str], fora: list[str], titulo="Sobre o projeto: problema, escopo e limites"):
    with st.expander(titulo, expanded=False, icon=":material/info:"):
        li = lambda xs: "".join(f"<li>{x}</li>" for x in xs)
        _html(f'<div class="escopo"><div><h4>O problema</h4>{problema}</div>'
                    f'<div><h4>Dentro do escopo</h4><ul>{li(dentro)}</ul></div>'
                    f'<div class="fora"><h4>Fora do escopo</h4><ul>{li(fora)}</ul></div></div>',
                    )


def como_ler(itens: list[tuple[str, str, str]], titulo="Como ler esta aba: o que cada valor significa"):
    """itens = (nome, unidade/fórmula, explicação)."""
    with st.expander(titulo, icon=":material/menu_book:"):
        linhas = "".join(f"<tr><td>{n}</td><td>{u}</td><td>{e}</td></tr>" for n, u, e in itens)
        _html(f'<table class="glossario">{linhas}</table>')


def lead(texto: str):
    _html(f'<div class="lead">{texto}</div>')


def eyebrow(texto: str):
    _html(f'<div class="eyebrow">{texto}</div>')


def caixa(texto: str):
    _html(f'<div class="box">{texto}</div>')


def dica(texto: str):
    _html(f'<div class="hint">{texto}</div>')


def resultado(num: str, texto: str):
    _html(f'<div class="result"><div class="num">{num}</div>{texto}</div>')
