"""
HAR Tree Analyzer — FastAPI Backend
────────────────────────────────────
Endpoints
  POST /api/analyze              Upload HAR files → request/response tree
  POST /api/filter-auth          Filter tree → auth-relevant nodes only
  POST /api/filter-custom        Filter tree → custom keyword nodes
  POST /api/validate-filter-config  Validate a CustomFilterConfig JSON
  GET  /api/health               Health-check
  GET  /                         Embedded HTML tree explorer (bonus)
  GET  /docs                     Swagger UI
"""
from __future__ import annotations

import json
from typing import Any, Dict, List

import os
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse

from auth_filter import filter_auth_tree
from custom_filter import filter_custom_tree
from har_processor import build_tree, filter_noise, parse_har_files
from models import AnalyzeResponse, CustomFilterConfig, CustomFilterRequest, RequestNode

AnalyzeResponse.model_rebuild()

# ── App setup ──────────────────────────────────────────────────────────────────

app = FastAPI(
    title="HAR Tree Analyzer API",
    version="2.0.0",
    description=(
        "Parse HAR files into a request/response tree and filter it by auth "
        "flows or custom keywords.  Designed to be consumed by UI agents and "
        "the Streamlit frontend."
    ),
    swagger_ui_parameters={"defaultModelsExpandDepth": -1},
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── /api/health ────────────────────────────────────────────────────────────────

@app.get("/api/health", tags=["Meta"])
async def health():
    return {"status": "ok", "version": "2.0.0"}


# ── /api/analyze ──────────────────────────────────────────────────────────────

@app.post(
    "/api/analyze",
    tags=["Analysis"],
    summary="Upload HAR files and build a request/response tree",
    response_description="Full tree rooted at root_url + summary stats",
)
async def analyze(
    root_url: str = Form(..., description="Root URL — e.g. https://app.example.com"),
    har_files: List[UploadFile] = File(..., description="One or more .har files"),
):
    if not root_url.startswith(("http://", "https://")):
        raise HTTPException(400, "root_url must start with http:// or https://")

    har_contents = []
    for f in har_files:
        if f.filename and not f.filename.lower().endswith(".har"):
            raise HTTPException(400, f"'{f.filename}' is not a .har file")
        content = await f.read()
        har_contents.append((f.filename or "unknown.har", content))

    if not har_contents:
        raise HTTPException(400, "No HAR files provided")

    try:
        raw_entries = parse_har_files(har_contents)
        clean_entries, stats = filter_noise(raw_entries)
        tree, orphans = build_tree(clean_entries, root_url)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc

    result = AnalyzeResponse(
        root_url=root_url,
        har_files=[f[0] for f in har_contents],
        total_entries_raw=stats.total_raw,
        total_entries_filtered=stats.after_noise_filter,
        noise_removed=stats.total_raw - stats.after_noise_filter,
        tree=tree,
        orphan_nodes=orphans,
        summary=_build_summary(tree, orphans, stats),
    )
    return JSONResponse(content=result.model_dump())


# ── /api/default-filter ──────────────────────────────────────────────────────

@app.get(
    "/api/default-filter",
    tags=["Filters"],
    summary="Return the built-in default auth filter config",
)
async def get_default_filter():
    """Serve the bundled default_filter.json as a CustomFilterConfig."""
    config_path = Path(__file__).parent / "default_filter.json"
    if not config_path.exists():
        raise HTTPException(404, "default_filter.json not found on server")
    with open(config_path, encoding="utf-8") as fh:
        return JSONResponse(content=json.load(fh))


# ── /api/filter-auth ─────────────────────────────────────────────────────────

@app.post(
    "/api/filter-auth",
    tags=["Filters"],
    summary="Filter tree to only auth-relevant nodes",
    description=(
        "Pass the JSON output of `/api/analyze` as the request body.  "
        "Returns a filtered tree that retains only nodes involved in "
        "authentication / authorisation flows — OAuth, OIDC, SAML, Cognito, "
        "session cookies, token endpoints, redirects, etc.  Any node that "
        "matches keeps its entire branch."
    ),
)
async def filter_auth(payload: Dict[str, Any]):
    if "tree" not in payload:
        raise HTTPException(
            400, "Payload must contain a 'tree' key (use output of /api/analyze)"
        )
    try:
        result = filter_auth_tree(payload)
    except Exception as exc:
        raise HTTPException(422, f"Auth filter failed: {exc}") from exc
    return JSONResponse(content=result)


# ── /api/filter-custom ────────────────────────────────────────────────────────

@app.post(
    "/api/filter-custom",
    tags=["Filters"],
    summary="Filter tree by custom keywords",
    description=(
        "Pass the JSON output of `/api/analyze` (or `/api/filter-auth`) as "
        "`tree`/`orphan_nodes` plus a `config` block.  "
        "Two modes are supported:\n\n"
        "- **any_field** – keyword lists per field (URL, req/res headers, "
        "req/res body); a node matches if any keyword appears in the "
        "corresponding field.  The full branch below a match is preserved.\n\n"
        "- **keyword_list** – AND semantics; a branch is kept when the "
        "accumulated text from root to the node collectively contains *all* "
        "keywords.  Individual field filters are ignored in this mode."
    ),
)
async def filter_custom(body: CustomFilterRequest):
    payload = {
        "root_url":               body.root_url,
        "har_files":              body.har_files,
        "tree":                   body.tree,
        "orphan_nodes":           body.orphan_nodes,
        "total_entries_filtered": body.total_entries_filtered,
    }
    try:
        result = filter_custom_tree(payload, body.config)
    except Exception as exc:
        raise HTTPException(422, f"Custom filter failed: {exc}") from exc
    return JSONResponse(content=result)


# ── /api/validate-filter-config ──────────────────────────────────────────────

@app.post(
    "/api/validate-filter-config",
    tags=["Filters"],
    summary="Validate a CustomFilterConfig JSON",
    description=(
        "Accepts a raw JSON object and validates it against the "
        "CustomFilterConfig schema.  Returns the parsed config on success or "
        "a 422 with a detailed error on failure.  Use this before saving a "
        "config file or before applying an uploaded config."
    ),
)
async def validate_filter_config(payload: Dict[str, Any]):
    try:
        cfg = CustomFilterConfig.model_validate(payload)
        return JSONResponse(content={"valid": True, "config": cfg.model_dump()})
    except Exception as exc:
        raise HTTPException(422, {"valid": False, "error": str(exc)}) from exc


# ── / HTML explorer ───────────────────────────────────────────────────────────

@app.get(
    "/",
    response_class=HTMLResponse,
    tags=["UI"],
    summary="Embedded HTML tree explorer",
    include_in_schema=False,
)
def ui():
    return HTMLResponse(content=_html_ui(), status_code=200)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _build_summary(tree: RequestNode, orphans: List[RequestNode], stats) -> Dict[str, Any]:
    all_nodes: List[RequestNode] = []
    _flatten(tree, all_nodes)
    methods: Dict[str, int] = {}
    statuses: Dict[str, int] = {}
    types: Dict[str, int] = {}
    max_depth = 0
    for n in all_nodes:
        methods[n.method] = methods.get(n.method, 0) + 1
        s_key = f"{n.status // 100}xx"
        statuses[s_key] = statuses.get(s_key, 0) + 1
        types[n.node_type] = types.get(n.node_type, 0) + 1
        if n.depth > max_depth:
            max_depth = n.depth
    return {
        "total_nodes_in_tree": len(all_nodes),
        "orphan_nodes": len(orphans),
        "max_tree_depth": max_depth,
        "by_method": methods,
        "by_status_class": statuses,
        "by_node_type": types,
        "noise_filter": {
            "total_raw": stats.total_raw,
            "after_filter": stats.after_noise_filter,
            "removed": stats.total_raw - stats.after_noise_filter,
            "breakdown": stats.noise_types,
        },
    }


def _flatten(node: RequestNode, out: List[RequestNode]):
    out.append(node)
    for child in node.children:
        _flatten(child, out)


# ── Minimal passthrough HTML UI ───────────────────────────────────────────────

def _html_ui() -> str:
    return """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>HAR Tree Analyzer API</title>
<style>
  body { background:#0d1117; color:#e6edf3; font-family:system-ui; display:flex;
         align-items:center; justify-content:center; height:100vh; margin:0; flex-direction:column; gap:16px; }
  a { color:#58a6ff; font-size:1.1rem; }
  p { color:#8b949e; font-size:.9rem; }
</style>
</head>
<body>
  <h1 style="font-size:1.5rem">🔍 HAR Tree Analyzer API v2</h1>
  <p>Use the Streamlit UI or the API directly.</p>
  <a href="/docs">📖 Swagger Docs</a>
  <a href="http://localhost:8501" target="_blank">🖥  Open Streamlit UI →</a>
</body>
</html>"""
