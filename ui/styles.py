"""Custom CSS: warm neutral background, restrained green accent, readable typography."""

import inspect

import streamlit as st

# `use_container_width` is deprecated in newer Streamlit in favour of width="stretch"
STRETCH: dict = ({"width": "stretch"} if "width" in inspect.signature(st.button).parameters
                 else {"use_container_width": True})

CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=DM+Sans:wght@400;500;600;700&family=Fraunces:opsz,wght@9..144,500;9..144,600&display=swap');
:root {
  --nosh-green: #2F7D4F; --nosh-green-dark: #245f3d; --nosh-green-soft: #E4F0E8;
  --nosh-ink: #1F2A24; --nosh-muted: #66736B; --nosh-line: #E3DCCD; --nosh-card: #FFFFFF;
  --nosh-amber: #8A5A00; --nosh-amber-soft: #FBEFD5; --nosh-red: #9B2C2C; --nosh-red-soft: #F8E1E0;
  --nosh-grey-soft: #ECE8DF; --nosh-blue: #285E8E; --nosh-blue-soft: #E1EDF7;
}
html, body, .stApp, .stMarkdown, .stButton button, .stTextInput input, .stTextArea textarea,
[data-testid="stCaptionContainer"], [data-testid="stMetric"], label, p, li {
  font-family: 'DM Sans', system-ui, -apple-system, 'Segoe UI', sans-serif; }
/* never override the icon font */
[data-testid="stIconMaterial"], .material-symbols-rounded, [class*="material-symbols"] {
  font-family: 'Material Symbols Rounded', 'Material Symbols Outlined' !important; }
h1, h2, h3 { font-family: 'Fraunces', Georgia, 'Times New Roman', serif; letter-spacing: -0.01em; color: var(--nosh-ink); }
.block-container { padding-top: 2.2rem; padding-bottom: 4rem; max-width: 1180px; }
[data-testid="stSidebar"] { border-right: 1px solid var(--nosh-line); }
.stButton > button, .stDownloadButton > button, [data-testid="stFormSubmitButton"] > button {
  border-radius: 10px; font-weight: 600; border: 1px solid var(--nosh-line);
}
.stButton > button[kind="primary"], [data-testid="stFormSubmitButton"] > button[kind="primaryFormSubmit"] {
  background: var(--nosh-green); border-color: var(--nosh-green); color: #fff;
}
.stButton > button[kind="primary"]:hover { background: var(--nosh-green-dark); border-color: var(--nosh-green-dark); }
[data-testid="stMetric"] { background: var(--nosh-card); border: 1px solid var(--nosh-line); border-radius: 14px; padding: 14px 16px; }
[data-testid="stMetricLabel"] p { color: var(--nosh-muted); font-size: .85rem; }
[data-testid="stVerticalBlockBorderWrapper"] { border-radius: 14px; }

.nosh-hero { background: linear-gradient(180deg, #F3EEE3 0%, #FAF7F2 100%); border: 1px solid var(--nosh-line);
  border-radius: 20px; padding: 36px 36px 30px 36px; margin-bottom: 1.2rem; }
.nosh-hero h1 { font-size: 2.5rem; margin: 0 0 .25rem 0; }
.nosh-hero .tag { color: var(--nosh-green); font-weight: 700; letter-spacing: .08em; font-size: .78rem; text-transform: uppercase; }
.nosh-hero p { color: var(--nosh-muted); font-size: 1.05rem; max-width: 760px; margin: .4rem 0 0 0; }
.nosh-pagehead h1 { font-size: 2rem; margin-bottom: .1rem; }
.nosh-pagehead p { color: var(--nosh-muted); margin-top: 0; }

.nosh-card { background: var(--nosh-card); border: 1px solid var(--nosh-line); border-radius: 14px; padding: 16px 18px; height: 100%; }
.nosh-card h4 { margin: 0 0 .25rem 0; font-size: 1.05rem; }
.nosh-card p { margin: 0; color: var(--nosh-muted); font-size: .93rem; }
.nosh-feature .icon { font-size: 1.5rem; }
.nosh-recipe-title { font-family: 'Fraunces', Georgia, serif; font-size: 1.18rem; font-weight: 600; color: var(--nosh-ink); }
.nosh-id { font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; font-size: .78rem; color: var(--nosh-muted);
  background: var(--nosh-grey-soft); padding: 1px 7px; border-radius: 6px; }
.nosh-meta { color: var(--nosh-muted); font-size: .85rem; margin: .15rem 0 .5rem 0; }

.nosh-chip { display: inline-block; padding: 2px 10px; margin: 2px 4px 2px 0; border-radius: 999px; font-size: .82rem;
  font-weight: 500; border: 1px solid transparent; line-height: 1.5; }
.nosh-chip.ok { background: var(--nosh-green-soft); color: var(--nosh-green-dark); border-color: #cfe5d6; }
.nosh-chip.warn { background: var(--nosh-amber-soft); color: var(--nosh-amber); border-color: #f0dcae; }
.nosh-chip.bad { background: var(--nosh-red-soft); color: var(--nosh-red); border-color: #efc7c5; }
.nosh-chip.muted { background: var(--nosh-grey-soft); color: var(--nosh-muted); }
.nosh-chip.info { background: var(--nosh-blue-soft); color: var(--nosh-blue); border-color: #c9dcee; }
.nosh-label { font-size: .78rem; font-weight: 700; letter-spacing: .05em; text-transform: uppercase; color: var(--nosh-muted); margin: .55rem 0 .1rem 0; }
.nosh-step { display: flex; gap: 12px; margin: 0 0 .7rem 0; }
.nosh-step .n { flex: 0 0 28px; height: 28px; border-radius: 50%; background: var(--nosh-green-soft); color: var(--nosh-green-dark);
  font-weight: 700; font-size: .85rem; display: flex; align-items: center; justify-content: center; margin-top: 1px; }
.nosh-step .t { flex: 1; line-height: 1.5; }
.nosh-step.changed .t { background: var(--nosh-amber-soft); border-radius: 8px; padding: 4px 8px; }
.nosh-line { padding: 5px 0; border-bottom: 1px dashed var(--nosh-line); }
.nosh-line.changed { background: var(--nosh-amber-soft); border-radius: 6px; padding: 5px 8px; border-bottom: none; }
.nosh-note { color: var(--nosh-muted); font-size: .85rem; }
.nosh-formula { font-family: ui-monospace, Menlo, Consolas, monospace; font-size: .8rem; color: var(--nosh-muted); }
@media (max-width: 640px) { .nosh-hero { padding: 22px 18px; } .nosh-hero h1 { font-size: 1.8rem; } }
</style>
"""


def inject() -> None:
    st.markdown(CSS, unsafe_allow_html=True)
