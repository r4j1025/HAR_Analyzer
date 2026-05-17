# HAR Tree Analyzer v2

Parse browser HAR files into a navigable request/response tree, then filter it
by **auth flows** or **custom keywords** — built for both humans and AI agents.

## Architecture

```
┌─────────────────────────────────────┐
│          Streamlit UI (8501)         │
│  Home.py       pages/Custom_Filter  │
│     └── utils/api_client.py  ───────┼──► FastAPI (8000)
│     └── utils/tree_renderer.py      │       ├── /api/analyze
└─────────────────────────────────────┘       ├── /api/filter-auth
                                              ├── /api/filter-custom
                                              └── /api/validate-filter-config
```

All UI interactions go through the REST API — making every feature accessible
to AI agents via HTTP without touching the Streamlit layer.

## Quick Start

```bash
# one command: installs deps and starts both services
./run.sh

# or manually:
cd backend  && pip install -r requirements.txt && uvicorn main:app --reload --port 8000
cd frontend && pip install -r requirements.txt && streamlit run Home.py
```

Open **http://localhost:8501** for the UI, **http://localhost:8000/docs** for
the Swagger API explorer.

## Features

### Tree View
- Full request/response tree rooted at your chosen URL
- Expand/collapse nodes, click to inspect full headers + body
- Real-time URL / method / status search
- Copy node JSON, cURL command, or full tree JSON
- Orphan nodes (cross-domain) shown in a separate panel

### Auth Filter (`POST /api/filter-auth`)
Preserves nodes and their entire branches if they touch:
- OAuth 2.0 / OIDC flows (authorize, token, userinfo, JWKS)
- AWS Cognito (InitiateAuth, RespondToAuthChallenge, …)
- SAML / SSO endpoints
- Session & auth cookies
- Authorization headers, 401/403 responses
- Login / logout / password-reset paths

### Custom Filter (`POST /api/filter-custom`)

**Field Keywords mode** (`match_mode: "any_field"`):  
Add keyword lists per field — URL, request headers, response headers, request
body, response body. A node matches if any keyword appears in the corresponding
field. The entire subtree below a match is preserved.

**AND List mode** (`match_mode: "keyword_list"`):  
Add multiple keywords; a branch is kept only when *all* keywords appear
somewhere in the accumulated text from the tree root down to that node. Useful
for tracing multi-step flows (e.g. keyword A in an early request, keyword B in
a later response on the same path).

Filter configs can be **saved as JSON** and **re-uploaded** in future sessions.

## API Reference

### `POST /api/analyze`
```
form-data:
  root_url  string   https://app.example.com
  har_files file[]   one or more .har files
```
Returns the full tree JSON.

### `POST /api/filter-auth`
```json
Body: <output of /api/analyze>
```
Returns auth-filtered tree.

### `POST /api/filter-custom`
```json
{
  "root_url": "...",
  "tree": { ... },
  "orphan_nodes": [ ... ],
  "config": {
    "name": "My Filter",
    "match_mode": "any_field",
    "url_keywords": ["oauth", "/token"],
    "req_header_keywords": ["Authorization"],
    "res_header_keywords": ["Set-Cookie"],
    "req_body_keywords": ["grant_type"],
    "res_body_keywords": ["access_token"]
  }
}
```

### `POST /api/validate-filter-config`
```json
Body: <CustomFilterConfig JSON>
```
Returns `{"valid": true, "config": {...}}` or `{"valid": false, "error": "..."}`.

## Filter Config Schema

```json
{
  "version": "1.0",
  "name": "string",
  "description": "string (optional)",
  "match_mode": "any_field | keyword_list",

  // used when match_mode == "any_field"
  "url_keywords":        ["string"],
  "req_header_keywords": ["string"],
  "res_header_keywords": ["string"],
  "req_body_keywords":   ["string"],
  "res_body_keywords":   ["string"],

  // used when match_mode == "keyword_list"
  "keyword_list": ["string"]
}
```

## Project Layout

```
har-analyzer/
├── backend/
│   ├── main.py            FastAPI app + all endpoints
│   ├── models.py          Pydantic models (RequestNode, CustomFilterConfig …)
│   ├── har_processor.py   HAR parsing → RequestNode tree
│   ├── auth_filter.py     Auth-flow filter logic
│   ├── custom_filter.py   Custom keyword filter logic
│   └── requirements.txt
├── frontend/
│   ├── Home.py            Main Streamlit page (upload, tree, filter buttons)
│   ├── pages/
│   │   └── Custom_Filter.py   Keyword config UI
│   ├── utils/
│   │   ├── api_client.py      HTTP wrapper for backend
│   │   └── tree_renderer.py   Self-contained HTML tree component
│   └── requirements.txt
├── .streamlit/config.toml
├── run.sh
└── README.md
```
