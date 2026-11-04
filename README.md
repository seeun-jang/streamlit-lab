# GlucoBridge — blood glucose & lifestyle journal (prototype)

A polished bilingual Streamlit prototype for a glucose log, analytics, AI explanations, visit-ready exports, and a **session-only** healthy-habits community demo. The heart-hugging blood-drop mascot is in `assets/mascot.png`.

> Educational / portfolio prototype only. It is not a medical device, doesn't provide diagnoses or dosing advice, and is not ready for storage or processing of real patient data.

## Project structure

```text
GlucoBridge/
├── app.py                        # Streamlit interface, bilingual UI, demo community
├── vitalog_core.py               # Validation, statistics, CSV, visit report HTML
├── requirements.txt
├── assets/
│   └── mascot.png
├── .streamlit/
│   ├── config.toml
│   └── secrets.toml.example
└── README.md
```

## Run locally

In a terminal inside the `GlucoBridge` folder:

```bash
python -m pip install -r requirements.txt
streamlit run app.py
```

Python 3.11+ is recommended.

### Enable Gemini AI

Create `.streamlit/secrets.toml` (never commit it), based on `secrets.toml.example`:

```toml
GEMINI_API_KEY = "YOUR_REAL_KEY"
GEMINI_MODEL = "gemini-3.5-flash-lite"
```

The app works without an API key for manual logging, charts, bilingual print-ready reports, CSV and community demo. AI requests require a valid key and permissions for the configured model. **Only when the user opts in** will calculated statistics be included in an AI request. The submitted question is still sent to the AI provider. Notes and raw readings are not included automatically.

### Deploy on Streamlit Community Cloud

1. Create or update a GitHub repo with `app.py`, `vitalog_core.py`, `requirements.txt`, `assets/mascot.png`, `.streamlit/config.toml`.
2. Select the repo and choose `app.py` as the main file.
3. Add the API key using the app's **Settings → Secrets** (not in GitHub).
4. Deploy, then try **Load demo data**.

## Functionality

- Patient-management / general-wellness interface modes, Korean / English UI.
- Manual glucose and HbA1c log with timestamps, context, measurement methods and notes.
- Scatter timeline of the **entered readings only**; no invented measurements between points.
- Statistics grouped by context and measurement method; mg/dL ⇄ mmol/L display.
- Gemini-powered optional explanations of computed summary metrics, with a consent checkbox.
- Bilingual print-ready report in HTML (browser Print → Save to PDF); optional separately labeled AI note when explicitly chosen; downloadable CSV backup.
- Diet / exercise / lifestyle posts, likes and comments **only in the current session**; not an online community.
- Compatible with CSV files produced by the old VITALOG prototype.

## What is deliberately out of scope

- Real accounts or shared community posts; user authentication, permanent data storage, moderation and reporting tools.
- Automatic sharing with hospitals, clinician acceptance or EMR integrations.
- FHIR R5 export and CGM integration (possible future phases).
- Real medical alerts, diagnosis, medicine/insulin recommendations.
- Full production localization: currently storage and timestamps use KST (UTC+09:00); reports explicitly label that timezone.

## Data and privacy

Data stays in `st.session_state`, which is temporary and may be lost on refresh/reconnect. Export a CSV before leaving. No data is written to a persistent database. Do not use personally identifying information in this demo. The community demo does not provide actual content moderation; its usage rules are not a substitute for it.

## Quick smoke check

```bash
python -m py_compile app.py vitalog_core.py
python -c "from vitalog_core import demo_records,export_csv,import_csv; x=demo_records(); assert import_csv(export_csv(x))==x; print('OK',len(x))"
```
