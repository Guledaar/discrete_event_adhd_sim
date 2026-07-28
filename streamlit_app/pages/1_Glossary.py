"""Parameter and KPI glossary (Streamlit user guide only)."""

from pathlib import Path

import streamlit as st

_APP_DIR = Path(__file__).resolve().parent.parent
_GLOSSARY = _APP_DIR / "GLOSSARY.md"

st.set_page_config(page_title="Glossary", layout="wide")
st.title("Glossary")
st.markdown(
    """
Definitions for **parameters**, **KPIs**, and **Run 1–3** outputs shown in this app.
Waits are displayed in **years** unless noted otherwise.
"""
)

if _GLOSSARY.is_file():
    st.markdown(_GLOSSARY.read_text(encoding="utf-8"))
else:
    st.error("Glossary content is missing. Contact the app maintainer.")
