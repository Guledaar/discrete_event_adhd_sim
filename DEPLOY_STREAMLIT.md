# Streamlit Community Cloud deployment

Public URL via [share.streamlit.io](https://share.streamlit.io/).

## One-time setup

1. Push this repo to **GitHub** (include `demo.ipynb`, `requirements.txt`, `des/`, `streamlit_app/`, `figures/`, `GLOSSARY.md`).
2. Sign in at [share.streamlit.io](https://share.streamlit.io/) → **Create app**.
3. **Repository** + branch (e.g. `main`).
4. **Main file path:** `streamlit_app/app.py`
5. **Python version:** 3.10 (Advanced settings).
6. **Dependencies:** root **`requirements.txt`** only.

Do **not** put `environment.yml` at the **repo root** — Cloud would use conda instead of pip. Local Conda: **`conda/environment.yml`**.

7. **Deploy** → share the `*.streamlit.app` link.

After code changes: push to the connected branch or **Manage app → Reboot app**.

## Local smoke test (same as Cloud)

```bash
pip install -r requirements.txt
./run_streamlit.sh
```

## Deploy checklist

| Item | Location |
|------|----------|
| App entry | `streamlit_app/app.py` |
| Pages | `streamlit_app/pages/` |
| Pip deps | `requirements.txt` (root) |
| Model package | `des/` |
| Glossary page | `GLOSSARY.md` (root) |
| Pathway image | `figures/nhs-neurodevelopmental-pathway.png` |
| Local Conda (optional) | `conda/environment.yml` |
| Notebook tutorial | `demo.ipynb` |

## Troubleshooting

| Issue | Fix |
|-------|-----|
| `ModuleNotFoundError: scipy` | Commit `requirements.txt`, reboot app; no root `environment.yml`. |
| `ModuleNotFoundError: des` | Deploy latest `app.py` (adds repo root to `sys.path`). |
| Cloud uses conda | Remove root `environment.yml`; use `conda/environment.yml` only. |
