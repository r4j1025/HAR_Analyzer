# 🔍 HAR Tree Analyzer

Parse browser `.har` files into an interactive request/response tree. Instantly filter authentication flows, search by keywords across decoded content, trace OAuth 2.0 / OIDC / SAML / Cognito flows, and decode JWTs, Base64, SAML assertions, and URL-encoded payloads — all without touching raw JSON.

---

## What it does

- **Tree builder** — converts flat HAR entries into a parent → child request tree using Referer headers, redirect chains, and path-prefix matching
- **Noise filter** — automatically strips analytics, fonts, images, and CDN requests so only meaningful traffic is shown
- **Auth filter** — detects OAuth 2.0, OIDC, SAML 2.0, AWS Cognito, session cookies, and 40+ other auth signals
- **Custom filter** — keyword search across URL, headers, and request/response bodies with per-keyword weights and a weighted confidence score
- **Combination matching** — multi-field rules to confirm end-to-end flows (e.g. full SAML POST binding, PKCE exchange); supports partial-match percentage scoring
- **Protocol detection** — combined scoring from keyword weights and combination results gives a verdict (Confirmed / Likely / Possible / Not detected) with a transparent breakdown
- **Smart decode at ingestion** — all request/response bodies and header values are pre-decoded at HAR upload time through a multi-layer pipeline (URL → JWT → Base64 → SAML Deflate → zlib inflate → JSON → HTML entities → Hex) so every keyword filter searches decoded content automatically
- **Inline decoder** — select any text in the UI to decode JWT, Base64, SAML Deflate, URL-encoded, XML, or Hex values; chained decoding (e.g. URL → Base64 → XML Pretty Print) with full history and revert
- **Smart body display** — JSON and form bodies rendered as key:value tables with decoded values shown inline; encoded values auto-decoded with method badge and "show original" toggle
- **Smart header display** — `Location` and similar headers with URL query strings (e.g. `SAMLRequest=`, `RelayState=`) are parsed into a decoded param table automatically

---

## Project structure

```
har_analyzer/
├── frontend/                    # Streamlit web UI
│   ├── Home.py                  # Main page — tree view, filters, verdict card
│   ├── pages/
│   │   └── Custom_Filter.py     # Custom filter builder — keywords, weights, combinations
│   ├── utils/
│   │   ├── api_client.py        # HTTP wrapper for FastAPI backend
│   │   └── tree_renderer.py     # Self-contained HTML/JS tree with inline decoder
│   └── requirements.txt
│
└── backend/                     # FastAPI REST API
    ├── main.py                  # API routes
    ├── har_processor.py         # HAR parsing, noise filtering, tree building, decode at ingestion
    ├── decoder.py               # Multi-layer decode pipeline (shared by ingestion and filter)
    ├── auth_filter.py           # Built-in auth signal detector
    ├── custom_filter.py         # Keyword + combination filter engine with scoring
    ├── models.py                # Pydantic models (RequestNode, CustomFilterConfig, CombinationEntry…)
    ├── default_filter.json      # Built-in default auth filter config
    ├── saml_filter.json         # SAML 2.0 filter with weighted keywords and combinations
    ├── oauth2_filter.json       # OAuth 2.0 filter
    ├── oidc_filter.json         # OpenID Connect filter
    └── requirements.txt
```

---

## How to capture a HAR file

HAR (HTTP Archive) files record every network request your browser makes. Follow these steps to capture the traffic you want to analyse.

1. Open the website you want to analyse in your browser.
2. Press **F12** to open Developer Tools (or right-click anywhere and choose **Inspect**).
3. Click the **Network** tab at the top of DevTools.
4. Inside Network settings, enable **"Allow to generate HAR with sensitive data"** — this ensures tokens, cookies, and request bodies are included.
5. Enable the recorder by clicking the **record button** in the top-left corner of the Network panel (it turns red when active).
6. Perform the actions you want to capture — for example, log in to the site, complete an SSO flow, or trigger an API call.
7. **If a button or link opens a new tab:** copy the link address, open a new tab manually, turn on the HAR recorder in that tab, then navigate to the link. This ensures all requests in the new tab are captured too.
8. Once done, right-click anywhere in the Network panel and choose **Save all as HAR with content** (Chrome) or **Save all as HAR** (Firefox/Edge). Make sure to use the option that includes sensitive data if available.
9. Save the files somewhere on your computer — for example `login_session.har` and `app_auth.har`. You can upload multiple HAR files together in the analyzer.

> ⚠ HAR files contain raw credentials, session tokens, and cookies. Never commit them to version control or share them publicly. Delete them after analysis.

---

## Getting started

You need **two terminals** running simultaneously — one for the backend API, one for the frontend UI.

### Terminal 1 — Backend (FastAPI)

```bash
cd har_analyzer/backend
python -m venv .venv        # first time only
.venv\Scripts\activate      # Windows
# source .venv/bin/activate   # Mac / Linux
pip install -r requirements.txt    # first time only
uvicorn main:app --reload --port 8000
```

API docs available at **http://localhost:8000/docs**

### Terminal 2 — Frontend (Streamlit UI)

```bash
cd har_analyzer/frontend
python -m venv .venv        # first time only
.venv\Scripts\activate      # Windows
# source .venv/bin/activate   # Mac / Linux
pip install -r requirements.txt    # first time only
streamlit run Home.py --server.port 8501
```

Open **http://localhost:8501** in your browser.

> Start the backend before the frontend. The frontend health-checks the backend on load and shows a red indicator in the sidebar if it can't connect.

---

## Quick usage

1. Export one or more `.har` files from your browser (see steps above)
2. Open the Streamlit UI, enter your site's root URL (e.g. `https://app.example.com`) in the sidebar, and upload the HAR file(s)
3. Click **Analyze** — the request tree appears with noise already removed
4. Click **Custom Filter** to search by keywords, or load a pre-built filter (`saml_filter.json`, `oauth2_filter.json`, `oidc_filter.json`) to detect specific protocols
5. View the **Protocol Detection** verdict card for a confidence score with breakdown
6. Click any node in the tree to expand its request and response — encoded values are automatically decoded inline
7. Select any text in the detail panel to open the manual decoder with chaining support

---

## Filter JSON format

Custom filters are portable JSON files. Load them via the Custom Filter page or the API.

```jsonc
{
  "version": "1.0",
  "name": "SAML Filter",
  "description": "Detects SAML 2.0 authentication flows",
  "match_mode": "any_field",       // "any_field" or "keyword_list"

  // Weighted keyword lists — each entry is {keyword, weight} or a plain string
  "url_keywords":        [{ "keyword": "/saml/acs",    "weight": 10 }],
  "req_header_keywords": [{ "keyword": "SAMLResponse", "weight": 10 }],
  "res_header_keywords": [{ "keyword": "SAMLRequest",  "weight": 10 }],
  "req_body_keywords":   [{ "keyword": "saml:Issuer",  "weight": 9  }],
  "res_body_keywords":   [{ "keyword": "saml:NameID",  "weight": 9  }],

  // AND keyword list (match_mode = "keyword_list" only)
  "keyword_list": [],

  // Combinations — multi-field rules checked branch-by-branch
  "combinations": [
    {
      "name": "SAML POST Binding",
      "description": "SP receives assertion via HTTP POST",
      "url_keywords":        ["/saml/acs"],
      "req_body_keywords":   ["SAMLResponse", "RelayState"],
      "req_header_keywords": [],
      "res_header_keywords": [],
      "res_body_keywords":   []
    }
  ]
}
```

---

## Decode pipeline

At HAR upload time, every body and header value is expanded through these layers in order. The expanded text is stored alongside the original and searched by all filters — encoded values are never hidden from keyword matching.

| Layer | What it handles |
|---|---|
| URL decode | `%XX` sequences, `+` → space in form bodies |
| JWT | 3-part `header.payload.signature` — claims extracted as `key=value` |
| Base64 / Base64URL | Standard and URL-safe variants |
| SAML Deflate | URL-encoded → Base64 → `zlib.decompress(raw, -15)` (SAML Redirect Binding) |
| zlib inflate | Fallback when Base64 decodes to compressed binary |
| JSON | Recursive value expansion inside `{"key":"encoded_value"}` bodies |
| HTML entities | `&amp;` `&lt;` `&#60;` |
| Hex | Long even-length hex strings |
| Auth prefixes | `Bearer`, `Basic`, `Token` stripped before token decode |
| URL query params in headers | `Location: /path?SAMLRequest=...&RelayState=...` — each param decoded individually |

---

## API endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/api/analyze` | Upload HAR files → returns full decoded request tree |
| `POST` | `/api/filter-auth` | Filter tree to auth-relevant nodes |
| `POST` | `/api/filter-custom` | Filter tree by custom keyword + combination config |
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
- See `frontend/requirements.txt` and `backend/requirements.txt` for full package lists
- pako 2.1.0 (loaded from cdnjs in the browser — no install needed) for SAML Deflate decoding in the UI

---

## ⚠ Security note

HAR files contain raw HTTP traffic including session cookies, access tokens, SAML assertions, and API keys. Treat them as sensitive credentials:

- Never commit HAR files to version control
- Never share HAR files publicly or via unencrypted channels
- Delete HAR files after analysis is complete
- Consider redacting sensitive values before sharing the tool's output with others