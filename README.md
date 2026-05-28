# 🔍 HAR Tree Analyzer

Parse browser `.har` files into an interactive request/response tree. Instantly filter auth flows, search by keywords, decode JWTs and Base64 values inline, and trace OAuth / SAML / Cognito flows without reading raw JSON.

---

## What it does

- **Tree builder** — converts flat HAR entries into a parent → child request tree using Referer headers, redirect chains, and path-prefix matching
- **Noise filter** — automatically strips analytics, fonts, images, and CDN requests
- **Auth filter** — detects OAuth 2.0, OIDC, SAML, Cognito, session cookies, and 40+ other auth signals
- **Custom filter** — keyword search across URL, headers, and request/response bodies (with weights)
- **Combination matching** — multi-field rules to confirm end-to-end flows (e.g. full PKCE exchange)
- **Inline decoder** — select any text in the UI to decode JWT, Base64, URL-encoded, XML, or Hex values

---

## Project structure

```
har_analyzer/
├── frontend/          # Streamlit web UI
│   ├── Home.py
│   ├── pages/
│   │   └── Custom_Filter.py
│   ├── utils/
│   │   ├── api_client.py
│   │   └── tree_renderer.py
│   └── requirements.txt
│
└── backend/           # FastAPI REST API
    ├── main.py
    ├── har_processor.py
    ├── decoder.py
    ├── auth_filter.py
    ├── custom_filter.py
    ├── models.py
    ├── default_filter.json
    └── requirements.txt
```

---

## Getting started

You need **two terminals** running simultaneously — one for the frontend, one for the backend.

### Terminal 1 — Frontend (Streamlit UI)

```bash
cd har_analyzer
cd .\frontend\
python -m venv .venv        # only first time
.venv\Scripts\activate
pip install -r requirements.txt    # only first time
streamlit run Home.py --server.port 8501
```

Open **http://localhost:8501** in your browser.

### Terminal 2 — Backend (FastAPI)

```bash
cd har_analyzer
cd .\backend\
python -m venv .venv        # only first time
.venv\Scripts\activate
pip install -r requirements.txt    # only first time
uvicorn main:app --reload --port 8000
```

API docs available at **http://localhost:8000/docs**

> **Mac / Linux users:** replace `.venv\Scripts\activate` with `source .venv/bin/activate`

---

## Quick usage

1. Export a `.har` file from Chrome DevTools → Network tab → right-click → *Save all as HAR with content*
2. Open the Streamlit UI, enter your site's root URL (e.g. `https://app.example.com`), and upload the HAR
3. Click **Analyze** — the tree appears with noise already removed
4. Click **Auth Filter** to narrow the tree to authentication flows only
5. Use **Custom Filter** to search for specific keywords with weights and combinations

---

## API endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/api/analyze` | Upload HAR files → returns full request tree |
| `POST` | `/api/filter-auth` | Filter tree to auth-relevant nodes |
| `POST` | `/api/filter-custom` | Filter tree by custom keyword config |
| `GET`  | `/api/default-filter` | Return built-in default filter config |
| `POST` | `/api/validate-filter-config` | Validate a filter config JSON |
| `GET`  | `/api/health` | Health check |

---

## Screenshots

![alt text](<Screenshot 2026-05-09 124638.png>)

![alt text](<Screenshot 2026-05-28 125202.png>)

![alt text](<Screenshot 2026-05-28 125238.png>)

![alt text](<Screenshot 2026-05-28 125258.png>)

![alt text](<Screenshot 2026-05-28 125313.png>)

![alt text](<Screenshot 2026-05-28 125824.png>)

![alt text](<Screenshot 2026-05-28 125343.png>)

![alt text](<Screenshot 2026-05-28 125432.png>)

---

## Requirements

- Python 3.11.9+
- See `frontend/requirements.txt` and `backend/requirements.txt` for package lists

---

## ⚠ Security note

HAR files contain raw credentials, tokens, and cookies. Never commit them to version control or share them publicly.
