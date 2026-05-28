"""
HAR Parser & Tree Builder
─────────────────────────
Pipeline:
  parse_har_files()  →  raw entries (all HAR files merged)
  filter_noise()     →  meaningful HTTP traffic only
  build_tree()       →  RequestNode hierarchy rooted at root_url
"""
from __future__ import annotations

import hashlib
import json
import re
from collections import defaultdict
from typing import Any, Dict, List, Optional, Set, Tuple
from urllib.parse import parse_qs, urljoin, urlparse, urlunparse

from models import (
    CookieEntry,
    FilterStats,
    HeaderEntry,
    RequestDetail,
    RequestNode,
    ResponseDetail,
    TimingInfo,
)
from decoder import expand_body, expand_headers

# ---------------------------------------------------------------------------
# Noise filter configuration
# ---------------------------------------------------------------------------
NOISE_EXTENSIONS = {
    ".css", ".scss", ".less",
    ".png", ".jpg", ".jpeg", ".gif", ".svg", ".webp", ".avif", ".ico",
    ".woff", ".woff2", ".ttf", ".otf", ".eot",
    ".mp4", ".mp3", ".webm", ".ogg", ".wav", ".avi", ".mov",
    ".pdf", ".zip", ".gz", ".tar",
    ".map",
}

NOISE_CONTENT_TYPES = re.compile(
    r"^(text/css|image/|font/|audio/|video/|application/(font|x-font))",
    re.I,
)

NOISE_PATHS = re.compile(
    r"/(static|assets|_next/static|__webpack|webpack|chunks?|node_modules"
    r"|favicon|robots\.txt|sitemap|\.well-known)",
    re.I,
)

ANALYTICS_HOSTS = {
    "www.google-analytics.com", "analytics.google.com",
    "www.googletagmanager.com", "region1.google-analytics.com",
    "stats.g.doubleclick.net", "www.googleadservices.com",
    "bat.bing.com", "ct.pinterest.com",
    "analytics.tiktok.com", "www.facebook.com/tr",
    "pixel.facebook.com", "connect.facebook.net",
    "cdn.segment.com", "api.segment.io",
    "cdn.heapanalytics.com", "heapanalytics.com",
    "fullstory.com", "rs.fullstory.com",
    "logrocket.com", "cdn.logrocket.io",
    "sentry.io", "o0.ingest.sentry.io",
    "browser.sentry-cdn.com", "js.sentry-cdn.com",
    "datadoghq.com", "dd-data.datadoghq.com",
    "nr-data.net", "newrelic.com",
    "hotjar.com", "static.hotjar.com",
    "clarity.ms", "c.clarity.ms",
    "cdn.cookielaw.org", "consent.cookielaw.org",
    "www.recaptcha.net", "www.gstatic.com",
    "fonts.googleapis.com", "fonts.gstatic.com",
    "use.fontawesome.com", "kit.fontawesome.com",
    "cdn.jsdelivr.net", "unpkg.com", "cdnjs.cloudflare.com",
}

KEEP_CONTENT_TYPES = re.compile(
    r"^(application/(json|ld\+json|graphql|xml|x-www-form-urlencoded"
    r"|vnd\.|octet-stream)|text/(html|xml|plain)|multipart/)",
    re.I,
)


# ---------------------------------------------------------------------------
# Public entry points
# ---------------------------------------------------------------------------
def parse_har_files(har_contents: List[Tuple[str, bytes]]) -> List[dict]:
    """Merge all HAR file entries into one flat list."""
    merged: List[dict] = []
    for filename, content in har_contents:
        try:
            data = json.loads(content)
        except json.JSONDecodeError as exc:
            raise ValueError(f"Invalid JSON in HAR file '{filename}': {exc}") from exc

        if "log" not in data:
            raise ValueError(f"'{filename}' does not look like a valid HAR file (missing 'log' key)")

        entries = data["log"].get("entries", [])
        for e in entries:
            e["_source_har"] = filename
        merged.extend(entries)

    merged.sort(key=lambda e: e.get("startedDateTime", ""))
    return merged


def filter_noise(entries: List[dict]) -> Tuple[List[dict], FilterStats]:
    """Remove CSS, fonts, images, analytics, etc. Returns (clean_entries, stats)."""
    noise_counts: Dict[str, int] = defaultdict(int)
    clean: List[dict] = []

    for entry in entries:
        req = entry.get("request", {})
        resp = entry.get("response", {})
        url = req.get("url", "")
        parsed = urlparse(url)
        host = parsed.netloc.lower().split(":")[0]
        path = parsed.path.lower()
        ext = "." + path.rsplit(".", 1)[-1] if "." in path.split("/")[-1] else ""
        resp_ct = _get_header(resp.get("headers", []), "content-type") or ""

        if host in ANALYTICS_HOSTS:
            noise_counts["analytics/telemetry"] += 1
            continue

        if ext in NOISE_EXTENSIONS:
            noise_counts[f"file_ext:{ext}"] += 1
            continue

        if NOISE_CONTENT_TYPES.match(resp_ct.split(";")[0].strip()):
            noise_counts[f"content_type:{resp_ct.split(';')[0].strip()}"] += 1
            continue

        if NOISE_PATHS.search(path):
            if not KEEP_CONTENT_TYPES.match(resp_ct.split(";")[0].strip()):
                noise_counts["static_assets_path"] += 1
                continue

        clean.append(entry)

    stats = FilterStats(
        total_raw=len(entries),
        after_noise_filter=len(clean),
        noise_types=dict(noise_counts),
    )
    return clean, stats


# ---------------------------------------------------------------------------
# Tree builder
# ---------------------------------------------------------------------------
def build_tree(entries: List[dict], root_url: str) -> Tuple[RequestNode, List[RequestNode]]:
    """Build a RequestNode tree rooted at root_url. Returns (root_node, orphan_nodes)."""
    root_parsed = urlparse(root_url)
    root_host   = root_parsed.netloc.lower()
    root_domain = _extract_domain(root_host)

    nodes: List[RequestNode] = []
    for entry in entries:
        node = _entry_to_node(entry, root_domain)
        if node:
            nodes.append(node)

    root_node = RequestNode(
        id=_make_id(root_url),
        url=root_url,
        domain=root_host,
        path=root_parsed.path or "/",
        method="GET",
        status=200,
        status_text="OK",
        node_type="page",
        request=RequestDetail(method="GET", url=root_url, headers=[]),
        response=ResponseDetail(status=200, status_text="OK"),
        depth=0,
    )

    url_to_node: Dict[str, RequestNode] = {root_url: root_node}
    for n in nodes:
        url_to_node[n.url] = n

    assigned: Set[str] = set()

    # Pre-build a normalised-URL -> node map for fuzzy Referer matching.
    # Strips query string, fragment, and trailing slash so that
    # "https://app.com/login?next=/" and "https://app.com/login" both resolve
    # to the same node.
    norm_to_node: Dict[str, RequestNode] = {}
    for _url, _node in url_to_node.items():
        norm_to_node[_normalize_url(_url)] = _node

    def _find_referer_parent(node: RequestNode) -> Optional[RequestNode]:
        referer = _get_request_header(node, "referer")
        if not referer:
            return None
        # 1. Exact match
        candidate = url_to_node.get(referer)
        if candidate and candidate.id != node.id:
            return candidate
        # 2. Normalised match (drops query / fragment / trailing slash)
        candidate = norm_to_node.get(_normalize_url(referer))
        if candidate and candidate.id != node.id:
            return candidate
        return None

    # Pass 1: redirect chains
    for n in nodes:
        if n.response.redirect_url:
            target_url = n.response.redirect_url
            if target_url in url_to_node:
                child = url_to_node[target_url]
                if child.id not in assigned:
                    n.children.append(child)
                    assigned.add(child.id)

    # Pass 2: Referer header (exact + normalised, ANY domain)
    # Runs before the domain-split so that cross-domain calls triggered by a
    # known page (e.g. IDP POST whose Referer is /login) get attached to their
    # real parent instead of being sent to orphans.
    for n in nodes:
        if n.id in assigned:
            continue
        parent = _find_referer_parent(n)
        if parent:
            parent.children.append(n)
            assigned.add(n.id)

    # Pass 3: path-prefix matching (same domain only)
    same_domain = [n for n in nodes if n.id not in assigned and _extract_domain(n.domain) == root_domain]
    same_domain.sort(key=lambda n: len(n.path))

    for n in same_domain:
        if n.id in assigned:
            continue
        best_parent = _find_best_path_parent(n, same_domain, url_to_node, root_node)
        best_parent.children.append(n)
        assigned.add(n.id)

    # Pass 4: anything still unassigned
    # Cross-domain with no Referer link -> true orphan.
    # Same-domain stragglers -> hang off root.
    orphans: List[RequestNode] = []
    for n in nodes:
        if n.id not in assigned:
            if n.domain and _extract_domain(n.domain) != root_domain:
                orphans.append(n)
            else:
                root_node.children.append(n)
                assigned.add(n.id)

    root_node = _dedup_children(root_node)
    _set_depth(root_node, 0)

    return root_node, orphans


# ---------------------------------------------------------------------------
# Node construction
# ---------------------------------------------------------------------------
def _entry_to_node(entry: dict, root_domain: str) -> Optional[RequestNode]:
    req  = entry.get("request", {})
    resp = entry.get("response", {})
    url  = req.get("url", "")
    if not url:
        return None

    parsed = urlparse(url)
    qs = {}
    for k, v in parse_qs(parsed.query).items():
        qs[k] = v[0] if len(v) == 1 else v

    status      = resp.get("status", 0)
    status_text = resp.get("statusText", "")
    method      = req.get("method", "GET").upper()

    req_headers  = [HeaderEntry(name=h["name"], value=h["value"]) for h in req.get("headers", [])]
    resp_headers = [HeaderEntry(name=h["name"], value=h["value"]) for h in resp.get("headers", [])]

    req_cookies  = _parse_cookies(req.get("cookies", []))
    resp_cookies = _parse_cookies(resp.get("cookies", []))

    req_body, req_mime, req_body_parsed, req_body_decoded   = _parse_request_body(req)
    resp_body, resp_mime, resp_body_parsed, resp_body_decoded = _parse_response_body(resp)
    req_headers_decoded  = expand_headers(req_headers)
    resp_headers_decoded = expand_headers(resp_headers)

    redirect_url = None
    if status in (301, 302, 303, 307, 308):
        raw_loc = _get_header(resp.get("headers", []), "location")
        if raw_loc:
            redirect_url = urljoin(url, raw_loc)

    node_type = _classify_node_type(req, resp, parsed)

    return RequestNode(
        id=_make_id(f"{method}:{url}"),
        url=url,
        domain=parsed.netloc.lower(),
        path=parsed.path,
        method=method,
        status=status,
        status_text=status_text,
        node_type=node_type,
        request=RequestDetail(
            method=method,
            url=url,
            http_version=req.get("httpVersion", "HTTP/1.1"),
            headers=req_headers,
            cookies=req_cookies,
            query_params=qs,
            body=req_body,
            body_mime_type=req_mime,
            body_parsed=req_body_parsed,
            body_decoded=req_body_decoded,
            headers_decoded=req_headers_decoded,
        ),
        response=ResponseDetail(
            status=status,
            status_text=status_text,
            headers=resp_headers,
            cookies=resp_cookies,
            body=resp_body,
            body_mime_type=resp_mime,
            body_parsed=resp_body_parsed,
            redirect_url=redirect_url,
            body_decoded=resp_body_decoded,
            headers_decoded=resp_headers_decoded,
        ),
        timing=_parse_timing(entry),
        source_har=entry.get("_source_har"),
    )


def _classify_node_type(req: dict, resp: dict, parsed) -> str:
    status = resp.get("status", 0)
    if status in (301, 302, 303, 307, 308):
        return "redirect"
    method = req.get("method", "GET").upper()
    ct = _get_header(resp.get("headers", []), "content-type") or ""
    if "text/html" in ct and method == "GET":
        return "page"
    if "application/json" in ct or method in ("POST", "PUT", "PATCH", "DELETE"):
        return "api"
    upgrade = _get_header(req.get("headers", []), "upgrade") or ""
    if "websocket" in upgrade.lower():
        return "websocket"
    ct_accept = _get_header(req.get("headers", []), "accept") or ""
    if "text/event-stream" in ct_accept:
        return "sse"
    return "api"


# ---------------------------------------------------------------------------
# Body parsing
# ---------------------------------------------------------------------------
def _parse_request_body(req: dict):
    post = req.get("postData", {})
    if not post:
        return None, None, None, None
    mime = post.get("mimeType", "")
    text = post.get("text", "")
    parsed = None
    if "json" in mime:
        try:
            parsed = json.loads(text)
        except Exception:
            pass
    elif "x-www-form-urlencoded" in mime:
        parsed = {k: v[0] if len(v) == 1 else v for k, v in parse_qs(text).items()}
    elif post.get("params"):
        parsed = {p["name"]: p["value"] for p in post["params"]}
    return (text if text else None), mime, parsed, expand_body(text, parsed)


def _parse_response_body(resp: dict):
    content = resp.get("content", {})
    if not content:
        return None, None, None, None
    mime = content.get("mimeType", "")
    text = content.get("text", "")
    parsed = None
    if text and ("json" in mime or "javascript" in mime):
        try:
            parsed = json.loads(text)
        except Exception:
            pass
    return (text if text else None), mime, parsed, expand_body(text, parsed)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _parse_cookies(raw: list) -> List[CookieEntry]:
    out = []
    for c in raw:
        out.append(CookieEntry(
            name=c.get("name", ""),
            value=c.get("value", ""),
            domain=c.get("domain"),
            path=c.get("path"),
            expires=c.get("expires"),
            http_only=c.get("httpOnly"),
            secure=c.get("secure"),
            same_site=c.get("sameSite"),
        ))
    return out


def _parse_timing(entry: dict) -> TimingInfo:
    t = entry.get("timings", {})
    return TimingInfo(
        started_at=entry.get("startedDateTime"),
        total_ms=entry.get("time"),
        wait_ms=t.get("wait"),
        receive_ms=t.get("receive"),
    )


def _get_header(headers: list, name: str) -> Optional[str]:
    for h in headers:
        if isinstance(h, dict) and h.get("name", "").lower() == name.lower():
            return h.get("value")
    return None


def _get_request_header(node: RequestNode, name: str) -> Optional[str]:
    for h in node.request.headers:
        if h.name.lower() == name.lower():
            return h.value
    return None


def _normalize_url(url: str) -> str:
    """Strip query string, fragment, and trailing slash for loose URL matching."""
    p = urlparse(url)
    return urlunparse((p.scheme, p.netloc.lower(), p.path.rstrip("/") or "/", "", "", ""))


def _make_id(seed: str) -> str:
    return hashlib.sha1(seed.encode()).hexdigest()[:12]


def _extract_domain(host: str) -> str:
    parts = host.split(".")
    return ".".join(parts[-2:]) if len(parts) >= 2 else host


def _find_best_path_parent(
    node: RequestNode,
    candidates: List[RequestNode],
    url_map: Dict[str, RequestNode],
    fallback: RequestNode,
) -> RequestNode:
    best: RequestNode = fallback
    best_len = 0
    node_parts = node.path.rstrip("/").split("/")
    for c in candidates:
        if c.id == node.id:
            continue
        c_parts = c.path.rstrip("/").split("/")
        if node_parts[: len(c_parts)] == c_parts and len(c_parts) > best_len:
            best = c
            best_len = len(c_parts)
    return best


def _dedup_children(node: RequestNode) -> RequestNode:
    seen: Set[str] = set()
    unique: List[RequestNode] = []
    for child in node.children:
        if child.id not in seen:
            seen.add(child.id)
            unique.append(_dedup_children(child))
    node.children = unique
    return node


def _set_depth(node: RequestNode, depth: int):
    node.depth = depth
    for child in node.children:
        _set_depth(child, depth + 1)