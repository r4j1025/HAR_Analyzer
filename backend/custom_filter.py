"""
custom_filter.py
─────────────────
Three filter strategies + combination detection:

any_field      –  node-level; a node matches if any keyword from the relevant
                  field list appears in the corresponding part of request/response.

keyword_list   –  branch-level AND; a branch (root→node) is kept when the
                  accumulated text collectively contains ALL keywords.

combinations   –  always evaluated; each combination checks whether ALL its
                  field-specific keywords are present somewhere in a branch.
                  100% → Found | 1-99% → Partial (with %) | 0% → Not found.
"""
from __future__ import annotations

from typing import List, Optional

from decoder import expand_body, expand_header_value, expand_headers
from models import CombinationEntry, CustomFilterConfig, RequestNode




# ── Keyword entry helpers ──────────────────────────────────────────────────────

def _kw_str(entry) -> str:
    """Return the keyword string regardless of plain-string or weighted-dict format."""
    return entry["keyword"] if isinstance(entry, dict) else str(entry)


def _kw_weight(entry) -> int:
    """Return weight; default 5 for plain-string entries."""
    return int(entry.get("weight", 5)) if isinstance(entry, dict) else 5


# ── Text extraction helpers ────────────────────────────────────────────────────

def _fields(node: RequestNode) -> dict:
    """
    Return searchable text per logical field.

    Uses pre-decoded body_decoded and headers_decoded fields that were
    computed at ingestion time by decoder.py.  Falls back to runtime
    expansion if the decoded fields are absent (e.g. old tree data).
    """
    # ── Headers ──────────────────────────────────────────────────────────────
    req_hdrs = (
        node.request.headers_decoded
        or expand_headers(node.request.headers)
    )
    res_hdrs = (
        node.response.headers_decoded
        or expand_headers(node.response.headers)
    )

    # ── Cookies ──────────────────────────────────────────────────────────────
    req_cookie_text = " ".join(f"{c.name} {c.value}" for c in node.request.cookies)
    res_cookie_text = " ".join(
        f"{h.value}" for h in node.response.headers if h.name.lower() == "set-cookie"
    )

    # ── Bodies ───────────────────────────────────────────────────────────────
    # Use pre-decoded if available; fall back to runtime expand_body.
    req_body = (
        node.request.body_decoded
        or expand_body(node.request.body, node.request.body_parsed)
        or ""
    )
    res_body = (
        node.response.body_decoded
        or expand_body(node.response.body, node.response.body_parsed)
        or ""
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

_CATEGORY_MAP = [
    ("URL Keywords",             "url_keywords",        "URL"),
    ("Request Header Keywords",  "req_header_keywords", "Request Header"),
    ("Response Header Keywords", "res_header_keywords", "Response Header"),
    ("Request Body Keywords",    "req_body_keywords",   "Request Body"),
    ("Response Body Keywords",   "res_body_keywords",   "Response Body"),
    ("AND Keyword List",         "keyword_list",        None),
]

# Mapping from CombinationEntry field name → internal field key
_COMBO_FIELD_MAP = [
    ("url_keywords",        "url"),
    ("req_header_keywords", "req_header"),
    ("res_header_keywords", "res_header"),
    ("req_body_keywords",   "req_body"),
    ("res_body_keywords",   "res_body"),
]


# ── Match helpers ─────────────────────────────────────────────────────────────

def _get_matches(node: RequestNode, cfg: CustomFilterConfig) -> list:
    """Return {keyword, field, actual} for every keyword hit on this node."""
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
    keywords: List,
    ancestor_text: str = "",
    match_info: list = None,
) -> Optional[RequestNode]:
    if match_info is None:
        match_info = []

    current_text = ancestor_text + "\n" + _fields(node)["all"]
    kws = [_kw_str(kw).strip().lower() for kw in keywords if _kw_str(kw).strip()]

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
            kw     = _kw_str(raw_entry).strip()
            if not kw:
                continue
            weight = _kw_weight(raw_entry)
            all_hits = kw_to_hits.get(kw.lower(), [])
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


# ── Combination matching ───────────────────────────────────────────────────────

def _combo_check_branch(combo: CombinationEntry, branch_acc: dict) -> tuple:
    """
    Check a combination against accumulated branch field texts.
    Returns (matched_list, unmatched_list, total_count, pct).
    """
    matched   = []
    unmatched = []

    for cfg_field, field_key in _COMBO_FIELD_MAP:
        kw_list = getattr(combo, cfg_field, [])
        for kw_entry in kw_list:
            kw = kw_entry.strip() if isinstance(kw_entry, str) else str(kw_entry).strip()
            if not kw:
                continue
            label = _FIELD_LABELS[field_key]
            if _ci_contains(branch_acc[field_key], kw):
                matched.append({"keyword": kw, "field": label})
            else:
                unmatched.append({"keyword": kw, "field": label})

    total = len(matched) + len(unmatched)
    pct   = round(len(matched) / total * 100) if total > 0 else 0
    return matched, unmatched, total, pct


def _match_combinations_in_tree(
    root: Optional[RequestNode],
    orphans: List[RequestNode],
    combinations: List[CombinationEntry],
) -> list:
    """
    For every CombinationEntry, walk every branch (root→node) in the tree
    and all orphan nodes, tracking the best (highest-%) match found.

    Returns a list of result dicts:
      {name, description, status, match_pct, total_keywords,
       matched_keywords, unmatched_keywords, matching_branches}
    """
    if not combinations:
        return []

    _empty_acc = {k: "" for k in _FIELD_LABELS}

    results = []

    for combo in combinations:
        # Collect all keywords for display
        all_kw_labels = []
        for cfg_field, field_key in _COMBO_FIELD_MAP:
            for kw_entry in getattr(combo, cfg_field, []):
                kw = kw_entry.strip() if isinstance(kw_entry, str) else str(kw_entry).strip()
                if kw:
                    all_kw_labels.append({"keyword": kw, "field": _FIELD_LABELS[field_key]})
        total_kws = len(all_kw_labels)

        full_matches: list    = []
        best_pct: int         = 0
        best_matched: list    = []
        best_unmatched: list  = []

        def _walk(node: RequestNode, acc: dict, path: list):
            nonlocal best_pct, best_matched, best_unmatched

            f       = _fields(node)
            new_acc = {k: acc[k] + "\n" + f[k] for k in acc}
            new_path = path + [{"url": node.url, "method": node.method, "path": node.path}]

            matched, unmatched, total, pct = _combo_check_branch(combo, new_acc)

            if total > 0:
                if pct == 100:
                    full_matches.append({
                        "branch_path":      new_path,
                        "deepest_node_id":  node.id,
                        "deepest_url":      node.url,
                        "deepest_method":   node.method,
                        "deepest_path":     node.path,
                        "matched_keywords": matched,
                    })
                elif pct > best_pct:
                    best_pct       = pct
                    best_matched   = matched
                    best_unmatched = unmatched

            for child in node.children:
                _walk(child, new_acc, new_path)

        if root is not None:
            _walk(root, dict(_empty_acc), [])

        for orphan in orphans:
            f   = _fields(orphan)
            acc = {k: f[k] for k in _empty_acc}
            matched, unmatched, total, pct = _combo_check_branch(combo, acc)
            if total > 0:
                if pct == 100:
                    full_matches.append({
                        "branch_path":      [{"url": orphan.url, "method": orphan.method, "path": orphan.path}],
                        "deepest_node_id":  orphan.id,
                        "deepest_url":      orphan.url,
                        "deepest_method":   orphan.method,
                        "deepest_path":     orphan.path,
                        "matched_keywords": matched,
                    })
                elif pct > best_pct:
                    best_pct       = pct
                    best_matched   = matched
                    best_unmatched = unmatched

        if full_matches:
            results.append({
                "name":               combo.name,
                "description":        combo.description or "",
                "status":             "found",
                "match_pct":          100,
                "total_keywords":     total_kws,
                "matched_keywords":   full_matches[0]["matched_keywords"],
                "unmatched_keywords": [],
                "matching_branches":  full_matches[:5],
            })
        elif best_pct > 0:
            results.append({
                "name":               combo.name,
                "description":        combo.description or "",
                "status":             "partial",
                "match_pct":          best_pct,
                "total_keywords":     total_kws,
                "matched_keywords":   best_matched,
                "unmatched_keywords": best_unmatched,
                "matching_branches":  [],
            })
        else:
            results.append({
                "name":               combo.name,
                "description":        combo.description or "",
                "status":             "not_found",
                "match_pct":          0,
                "total_keywords":     total_kws,
                "matched_keywords":   [],
                "unmatched_keywords": all_kw_labels,
                "matching_branches":  [],
            })

    return results


# ── Protocol score ─────────────────────────────────────────────────────────────

_SATURATION_TOP_N = 5


def _compute_protocol_score(cfg: CustomFilterConfig, keyword_summary: dict) -> dict:
    """
    Weighted confidence score using saturation-threshold denominator.
    denominator = sum of top-N keyword weights (default N=5) so that
    finding the N strongest signals gives 100% confidence.
    """
    all_weights: list = []
    earned:      int  = 0
    evidence:    list = []

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

    top_n_weights    = sorted(all_weights, reverse=True)[:_SATURATION_TOP_N]
    saturation_point = sum(top_n_weights) or 1
    total_weight     = sum(all_weights)
    score            = min(100, round(earned / saturation_point * 100))

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

    keyword_summary    = _build_keyword_summary(cfg, match_info)
    protocol_score     = _compute_protocol_score(cfg, keyword_summary)

    # ── Combination matching ── always runs on the FULL original tree
    # (not the filtered sub-tree) so combinations catch cross-branch signals
    full_root:    Optional[RequestNode] = None
    full_orphans: List[RequestNode]     = []
    if tree_dict:
        full_root = RequestNode.model_validate(tree_dict)
    for od in orphan_dicts:
        full_orphans.append(RequestNode.model_validate(od))

    combination_results = _match_combinations_in_tree(
        full_root, full_orphans, cfg.combinations
    )

    return {
        "root_url":            payload.get("root_url", ""),
        "har_files":           payload.get("har_files", []),
        "total_custom_nodes":  _count(filtered_root) + len(filtered_orphans),
        "original_total":      payload.get("total_entries_filtered", 0),
        "tree":                filtered_root.model_dump(exclude_none=True) if filtered_root else None,
        "orphan_nodes":        [o.model_dump(exclude_none=True) for o in filtered_orphans],
        "filter_config":       cfg.model_dump(),
        "match_info":          match_info,
        "keyword_summary":     keyword_summary,
        "protocol_score":      protocol_score,
        "combination_results": combination_results,
    }