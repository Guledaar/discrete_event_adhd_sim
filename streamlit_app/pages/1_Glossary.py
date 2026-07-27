"""Parameter and KPI glossary."""

from pathlib import Path

import streamlit as st

_ROOT = Path(__file__).resolve().parent.parent.parent
_GLOSSARY = _ROOT / "GLOSSARY.md"

st.set_page_config(page_title="Glossary", layout="wide")
st.title("Glossary — parameters and KPIs")

st.markdown(
    "Canonical definitions for **model parameters** (`Experiment`) and **KPIs** "
    "(`RunReport`, Run 1–3). The text below is loaded from `GLOSSARY.md` in the project root "
    "(aligned with `des/run_report.KPI_LABELS` and `streamlit_app/kpi_display.py`)."
)

if _GLOSSARY.is_file():
    st.markdown(_GLOSSARY.read_text(encoding="utf-8"))
else:
    st.error(f"Glossary file not found: `{_GLOSSARY}`")
