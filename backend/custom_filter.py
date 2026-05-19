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


# ── Keyword entry helpers ──────────────────────────────────────────────────────
# Keywords are either plain strings ("token") or weighted dicts
# ({"keyword": "token", "weight": 9}).  These two helpers normalise access.

def _kw_str(entry) -> str:
    """Return the keyword string regardless of entry format."""
    return entry["keyword"] if isinstance(entry, dict) else entry


def _kw_weight(entry) -> int:
    """Return the weight (1-10); default 5 for plain-string entries."""
    return int(entry.get("weight", 5)) if isinstance(entry, dict) else 5


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
        for entry in keywords:
            kw = _kw_str(entry).strip()
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
    kws = [_kw_str(kw).lower() for kw in keywords if _kw_str(kw).strip()]

    if all(kw in current_text.lower() for kw in kws):
        hits = []
        f = _fields(node)
        for entry in keywords:
            kw = _kw_str(entry).strip()
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
        for raw_entry in keywords:
            kw = _kw_str(raw_entry).strip()
            if not kw:
                continue

            weight    = _kw_weight(raw_entry)
            all_hits  = kw_to_hits.get(kw.lower(), [])

            # For field-specific categories, only count hits from the right field.
            # For keyword_list (field_filter=None), accept hits from any field.
            if field_filter is not None:
                relevant_hits = [h for h in all_hits if h["field"] == field_filter]
            else:
                relevant_hits = all_hits

            entries.append({
                "keyword": kw,
                "weight":  weight,
                "matched": len(relevant_hits) > 0,
                "hits":    relevant_hits,
            })

        if entries:
            summary[cat_name] = entries

    return summary


# ── Protocol score ─────────────────────────────────────────────────────────────

# Number of top-weighted keywords whose combined weight defines "100% confident".
# A HAR only captures what the browser did — most keywords will simply be absent
# because that endpoint was never hit.  Dividing by the weight of ALL keywords
# (including ones that could never appear together) gives an unfairly low score.
# Instead we ask: "did we find the equivalent of the N strongest signals?"
_SATURATION_TOP_N = 5


def _compute_protocol_score(cfg: CustomFilterConfig, keyword_summary: dict) -> dict:
    """
    Compute a weighted confidence score using a saturation-threshold denominator.

    Rationale
    ---------
    A HAR file only records requests that actually happened, so most keywords in
    a large filter will simply be absent - not because the protocol is not in use,
    but because those endpoints were never hit during the recording.  Dividing by
    the total weight of all keywords punishes the score for absence of evidence,
    producing "Not detected" even when definitive signals (SAMLRequest,
    saml:Assertion) are present.

    Fix: denominator = sum of the top-N keyword weights (default N=5).
    Interpretation: "if you found signals equivalent to the 5 strongest possible
    keywords for this protocol, we are fully confident."  Scores above 100 are
    capped, so matching more than 5 strong keywords never penalises the result.

    Verdict thresholds (on the capped 0-100 scale):
      >= 70 -> Confirmed  |  >= 40 -> Likely  |  >= 15 -> Possible  |  < 15 -> Not detected
    """
    all_weights = []
    earned      = 0
    evidence    = []

    for cat_name, entries in keyword_summary.items():
        for entry in entries:
            w = entry.get("weight", 5)
            all_weights.append(w)
            if entry["matched"]:
                earned += w
                evidence.append({
                    "keyword":  entry["keyword"],
                    "category": cat_name,
                    "weight":   w,
                    "hits":     len(entry["hits"]),
                })

    # Saturation point = sum of the N highest weights in the whole config.
    # This is the weight you would earn by finding the N most important signals.
    top_n_weights    = sorted(all_weights, reverse=True)[:_SATURATION_TOP_N]
    saturation_point = sum(top_n_weights) or 1      # guard against empty config
    total_weight     = sum(all_weights)              # kept for display only

    # Cap at 100: finding more than N strong signals does not lower confidence.
    score = min(100, round(earned / saturation_point * 100))

    verdict = (
        "Confirmed"    if score >= 70 else
        "Likely"       if score >= 40 else
        "Possible"     if score >= 15 else
        "Not detected"
    )

    evidence.sort(key=lambda x: x["weight"], reverse=True)

    return {
        "protocol":         cfg.name,
        "score":            score,
        "earned":           earned,
        "saturation_point": saturation_point,
        "total_weight":     total_weight,
        "verdict":          verdict,
        "evidence":         evidence,
    }




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
    protocol_score  = _compute_protocol_score(cfg, keyword_summary)

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
        "protocol_score":     protocol_score,
    }