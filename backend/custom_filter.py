"""
custom_filter.py
─────────────────
Two filter strategies:

any_field  –  node-level matching; if a node's URL / headers / body contains
              ANY keyword from the configured lists, that node and its entire
              subtree are kept.  Ancestor nodes are kept as path nodes.

keyword_list (AND) –  branch-level matching; a branch (root → node) is kept
              when the *accumulated* text from root down to that node
              collectively contains ALL keywords in the list.

Match info  –  both strategies return `match_info`: a list of
              {node_id, url, path, method, status, matches[]} describing
              which keywords matched each node and the actual text found.

Keyword summary  –  `keyword_summary` is a new field in the output.
              It lists ALL keywords from the config (matched or not) grouped
              by category, each with a `matched` bool and a `hits` list so
              the UI can render ✅/❌ per keyword with result details.
"""
from __future__ import annotations

from typing import List, Optional

from models import CustomFilterConfig, RequestNode


# ── Text extraction helpers ────────────────────────────────────────────────────

def _fields(node: RequestNode) -> dict:
    """Return searchable text per logical field."""
    req_hdrs = "\n".join(f"{h.name}: {h.value}" for h in node.request.headers)
    res_hdrs = "\n".join(f"{h.name}: {h.value}" for h in node.response.headers)

    def _body_text(body, parsed):
        parts = [body or ""]
        if isinstance(parsed, dict):
            parts.append(" ".join(f"{k} {v}" for k, v in parsed.items()))
        elif isinstance(parsed, list):
            parts.append(str(parsed))
        return "\n".join(parts)

    req_body = _body_text(node.request.body, node.request.body_parsed)
    res_body = _body_text(node.response.body, node.response.body_parsed)

    req_cookie_text = " ".join(f"{c.name} {c.value}" for c in node.request.cookies)
    res_cookie_text = " ".join(
        f"{h.value}" for h in node.response.headers if h.name.lower() == "set-cookie"
    )

    return {
        "url":        node.url,
        "req_header": req_hdrs + "\n" + req_cookie_text,
        "res_header": res_hdrs + "\n" + res_cookie_text,
        "req_body":   req_body,
        "res_body":   res_body,
        "all":        "\n".join([node.url, req_hdrs, res_hdrs, req_body, res_body]),
    }


def _ci_contains(text: str, keyword: str) -> bool:
    return keyword.lower() in text.lower()


def _extract_context(text: str, keyword: str, context: int = 80) -> str:
    idx = text.lower().find(keyword.lower())
    if idx < 0:
        return ""
    start = max(0, idx - 20)
    end   = min(len(text), idx + len(keyword) + context)
    snippet = text[start:end].strip().replace("\n", " ").replace("\r", "").replace("\t", " ")
    return (snippet[:120] + "…") if len(snippet) > 120 else snippet


_FIELD_LABELS = {
    "url":        "URL",
    "req_header": "Request Header",
    "res_header": "Response Header",
    "req_body":   "Request Body",
    "res_body":   "Response Body",
}

# Map config field name → (display label, internal key)
_CATEGORY_MAP = [
    ("URL Keywords",             "url_keywords",        "URL"),
    ("Request Header Keywords",  "req_header_keywords", "Request Header"),
    ("Response Header Keywords", "res_header_keywords", "Response Header"),
    ("Request Body Keywords",    "req_body_keywords",   "Request Body"),
    ("Response Body Keywords",   "res_body_keywords",   "Response Body"),
    ("AND Keyword List",         "keyword_list",        None),  # None = any field
]


# ── Match helpers ─────────────────────────────────────────────────────────────

def _get_matches(node: RequestNode, cfg: CustomFilterConfig) -> list:
    """Return list of {keyword, field, actual} for every keyword hit on this node."""
    f = _fields(node)
    hits = []
    checks = [
        (cfg.url_keywords,        "url"),
        (cfg.req_header_keywords, "req_header"),
        (cfg.res_header_keywords, "res_header"),
        (cfg.req_body_keywords,   "req_body"),
        (cfg.res_body_keywords,   "res_body"),
    ]
    seen = set()
    for keywords, field in checks:
        for kw in keywords:
            kw = kw.strip()
            if not kw:
                continue
            key = (kw.lower(), field)
            if key in seen:
                continue
            if _ci_contains(f[field], kw):
                seen.add(key)
                hits.append({
                    "keyword": kw,
                    "field":   _FIELD_LABELS[field],
                    "actual":  _extract_context(f[field], kw),
                })
    return hits


def _matches_any_field(node: RequestNode, cfg: CustomFilterConfig) -> bool:
    return bool(_get_matches(node, cfg))


# ── any_field strategy ─────────────────────────────────────────────────────────

def _filter_any_field(
    node: RequestNode,
    cfg: CustomFilterConfig,
    match_info: list,
) -> Optional[RequestNode]:
    hits = _get_matches(node, cfg)
    if hits:
        match_info.append({
            "node_id": node.id,
            "url":     node.url,
            "path":    node.path,
            "method":  node.method,
            "status":  node.status,
            "matches": hits,
        })
        return node

    filtered_children: List[RequestNode] = []
    for child in node.children:
        result = _filter_any_field(child, cfg, match_info)
        if result is not None:
            filtered_children.append(result)

    if filtered_children:
        copy = node.model_copy(deep=False)
        copy.children = filtered_children
        return copy

    return None


# ── keyword_list (AND) strategy ────────────────────────────────────────────────

def _filter_keyword_list(
    node: RequestNode,
    keywords: List[str],
    ancestor_text: str = "",
    match_info: list = None,
) -> Optional[RequestNode]:
    if match_info is None:
        match_info = []

    current_text = ancestor_text + "\n" + _fields(node)["all"]
    kws = [kw.strip().lower() for kw in keywords if kw.strip()]

    if all(kw in current_text.lower() for kw in kws):
        hits = []
        f = _fields(node)
        for kw in keywords:
            kw = kw.strip()
            if not kw:
                continue
            for field, label in _FIELD_LABELS.items():
                if _ci_contains(f[field], kw):
                    hits.append({
                        "keyword": kw,
                        "field":   label,
                        "actual":  _extract_context(f[field], kw),
                    })
                    break
        if hits:
            match_info.append({
                "node_id": node.id,
                "url":     node.url,
                "path":    node.path,
                "method":  node.method,
                "status":  node.status,
                "matches": hits,
            })
        return node

    filtered_children: List[RequestNode] = []
    for child in node.children:
        result = _filter_keyword_list(child, keywords, current_text, match_info)
        if result is not None:
            filtered_children.append(result)

    if filtered_children:
        copy = node.model_copy(deep=False)
        copy.children = filtered_children
        return copy

    return None


# ── Keyword summary builder ────────────────────────────────────────────────────

def _build_keyword_summary(cfg: CustomFilterConfig, match_info: list) -> dict:
    """
    Build a per-category, per-keyword summary that includes ALL configured
    keywords (matched or not), so the UI can render ✅/❌ per keyword and
    show hit details beneath matched ones.

    Structure:
      {
        "URL Keywords": [
          {"keyword": "/oauth", "matched": true,  "hits": [{node_id, url, method, path, field, actual}, ...]},
          {"keyword": "/login", "matched": false, "hits": []},
          ...
        ],
        "Request Header Keywords": [...],
        ...
      }
    """
    # Build reverse index: lowercase_keyword → list of hit dicts
    kw_to_hits: dict = {}
    for record in match_info:
        for m in record.get("matches", []):
            kw_lower = m["keyword"].lower()
            if kw_lower not in kw_to_hits:
                kw_to_hits[kw_lower] = []
            kw_to_hits[kw_lower].append({
                "node_id": record["node_id"],
                "url":     record["url"],
                "method":  record["method"],
                "path":    record["path"],
                "field":   m["field"],
                "actual":  m["actual"],
            })

    summary: dict = {}
    for cat_name, cfg_field, field_filter in _CATEGORY_MAP:
        keywords: list = getattr(cfg, cfg_field, [])
        if not keywords:
            continue

        entries = []
        for kw in keywords:
            kw = kw.strip()
            if not kw:
                continue

            all_hits = kw_to_hits.get(kw.lower(), [])

            # For field-specific categories, only count hits from the right field.
            # For keyword_list (field_filter=None), accept hits from any field.
            if field_filter is not None:
                relevant_hits = [h for h in all_hits if h["field"] == field_filter]
            else:
                relevant_hits = all_hits

            entries.append({
                "keyword": kw,
                "matched": len(relevant_hits) > 0,
                "hits":    relevant_hits,
            })

        if entries:
            summary[cat_name] = entries

    return summary


# ── Public API ─────────────────────────────────────────────────────────────────

def _count(node: Optional[RequestNode]) -> int:
    if node is None:
        return 0
    return 1 + sum(_count(c) for c in node.children)


def _has_any_field_filter(cfg: CustomFilterConfig) -> bool:
    return any([
        cfg.url_keywords,
        cfg.req_header_keywords,
        cfg.res_header_keywords,
        cfg.req_body_keywords,
        cfg.res_body_keywords,
    ])


def filter_custom_tree(payload: dict, cfg: CustomFilterConfig) -> dict:
    tree_dict    = payload.get("tree")
    orphan_dicts: list = payload.get("orphan_nodes", [])

    filtered_root:    Optional[RequestNode] = None
    filtered_orphans: List[RequestNode]     = []
    match_info: list = []

    if tree_dict:
        root = RequestNode.model_validate(tree_dict)

        if cfg.match_mode == "keyword_list":
            if cfg.keyword_list:
                filtered_root = _filter_keyword_list(root, cfg.keyword_list,
                                                     match_info=match_info)
            else:
                filtered_root = root
        else:
            if _has_any_field_filter(cfg):
                filtered_root = _filter_any_field(root, cfg, match_info)
            else:
                filtered_root = root

    for od in orphan_dicts:
        orphan = RequestNode.model_validate(od)
        if cfg.match_mode == "keyword_list":
            if not cfg.keyword_list:
                filtered_orphans.append(orphan)
            else:
                result = _filter_keyword_list(orphan, cfg.keyword_list,
                                              match_info=match_info)
                if result is not None:
                    filtered_orphans.append(orphan)
        else:
            hits = _get_matches(orphan, cfg)
            if not _has_any_field_filter(cfg) or hits:
                filtered_orphans.append(orphan)
                if hits:
                    match_info.append({
                        "node_id": orphan.id,
                        "url":     orphan.url,
                        "path":    orphan.path,
                        "method":  orphan.method,
                        "status":  orphan.status,
                        "matches": hits,
                    })

    keyword_summary = _build_keyword_summary(cfg, match_info)

    return {
        "root_url":           payload.get("root_url", ""),
        "har_files":          payload.get("har_files", []),
        "total_custom_nodes": _count(filtered_root) + len(filtered_orphans),
        "original_total":     payload.get("total_entries_filtered", 0),
        "tree":               filtered_root.model_dump(exclude_none=True) if filtered_root else None,
        "orphan_nodes":       [o.model_dump(exclude_none=True) for o in filtered_orphans],
        "filter_config":      cfg.model_dump(),
        "match_info":         match_info,
        "keyword_summary":    keyword_summary,
    }