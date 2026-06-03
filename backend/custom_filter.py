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

    Headers: header *names* and decoded *values* are both included so that
    searching for e.g. "authorization" or "x-api-key" hits the header name
    even when the value alone would not match.  expand_headers() is called
    live so SAML/JWT in Location, Set-Cookie etc. are always decoded.
    Stored headers_decoded is appended as extra coverage.

    Query params: both *keys* and *values* are included.  Every value is run
    through _expand_value so SAMLRequest, JWT, base64 blobs in URL query
    strings are decoded before matching.

    Cookies: cookie names and values are included in the header fields so
    that a keyword search on a cookie name hits the req_header / res_header
    field as expected.

    Bodies: use pre-decoded body_decoded (ingestion-time) with live fallback.
    """
    from decoder import _expand_value  # local import avoids circular at module level

    # ── Query params: keys + decoded values ───────────────────────────────────
    qp_parts: list = []
    for k, v in (node.request.query_params or {}).items():
        sv = ", ".join(v) if isinstance(v, list) else str(v)
        # Include the key itself so keyword "code" hits ?code=...
        qp_parts.append(k)
        qp_parts.append(f"{k}={sv}")
        qp_parts.append(sv)
        for dec in _expand_value(sv):
            qp_parts.append(f"{k}={dec}")
            qp_parts.append(dec)
    qp_text = "\n".join(qp_parts)

    # ── Headers (names + decoded values) ─────────────────────────────────────
    # expand_headers() already emits "Name: value\nName: decoded_value" lines,
    # but we also emit bare header names so a search for "authorization" (the
    # name) always matches regardless of its value.
    def _headers_with_names(headers) -> str:
        name_lines = [h.name for h in headers]            # bare names
        expanded   = expand_headers(headers)              # "Name: value\n..."
        return "\n".join(name_lines) + "\n" + expanded

    req_hdrs_live   = _headers_with_names(node.request.headers)
    res_hdrs_live   = _headers_with_names(node.response.headers)
    req_hdrs_stored = node.request.headers_decoded or ""
    res_hdrs_stored = node.response.headers_decoded or ""
    req_hdrs = req_hdrs_live + ("\n" + req_hdrs_stored if req_hdrs_stored else "")
    res_hdrs = res_hdrs_live + ("\n" + res_hdrs_stored if res_hdrs_stored else "")

    # ── Cookies (names + values in header fields) ─────────────────────────────
    req_cookie_text = "\n".join(
        f"{c.name}\n{c.name}={c.value}\n{c.value}" for c in node.request.cookies
    )
    res_cookie_text = "\n".join(
        f"{h.value}" for h in node.response.headers if h.name.lower() == "set-cookie"
    )

    # ── Bodies ────────────────────────────────────────────────────────────────
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

    # ── URL: raw URL + decoded query-param keys/values ────────────────────────
    url_text = node.url + ("\n" + qp_text if qp_text else "")

    # ── Composite field texts ─────────────────────────────────────────────────
    req_header_text = "\n".join(filter(None, [req_hdrs, req_cookie_text]))
    res_header_text = "\n".join(filter(None, [res_hdrs, res_cookie_text]))

    # req_body also includes query-param keys/values so that per-field
    # "Request Body" keyword searches still hit URL-encoded form params
    req_body_text = "\n".join(filter(None, [req_body, qp_text]))

    all_text = "\n".join(filter(None, [
        url_text,
        req_header_text,
        res_header_text,
        req_body_text,
        res_body,
    ]))

    return {
        "url":        url_text,
        "req_header": req_header_text,
        "res_header": res_header_text,
        "req_body":   req_body_text,
        "res_body":   res_body,
        "all":        all_text,
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

_ALL_FIELD_KEYS_ORDERED = ["url", "req_header", "res_header", "req_body", "res_body"]


def _get_matches(node: RequestNode, cfg: CustomFilterConfig) -> list:
    """
    Return {keyword, field, actual, configured_field} for every keyword hit
    on this node.

    Two-pass search per keyword:
      Pass 1 — designated field (strict match).
      Pass 2 — fallback across all other fields so that keywords configured
                in the wrong field (e.g. SAMLRequest in res_header_keywords
                but actually in the URL query params) are still matched and
                attributed to the field where they were actually found.
    """
    f = _fields(node)
    hits = []
    checks = [
        (cfg.url_keywords,        "url"),
        (cfg.req_header_keywords, "req_header"),
        (cfg.res_header_keywords, "res_header"),
        (cfg.req_body_keywords,   "req_body"),
        (cfg.res_body_keywords,   "res_body"),
    ]
    # dedup key: (kw.lower(), configured_field) so the same keyword in two
    # different config lists is treated independently
    seen = set()
    for keywords, configured_field in checks:
        for entry in keywords:
            kw = _kw_str(entry).strip()
            if not kw:
                continue
            key = (kw.lower(), configured_field)
            if key in seen:
                continue
            seen.add(key)

            # Pass 1: check the configured field
            if _ci_contains(f[configured_field], kw):
                actual_field = configured_field
            else:
                # Pass 2: fallback — find which field actually has it
                actual_field = None
                for fk in _ALL_FIELD_KEYS_ORDERED:
                    if fk != configured_field and _ci_contains(f[fk], kw):
                        actual_field = fk
                        break

            if actual_field is not None:
                hits.append({
                    "keyword":          kw,
                    "field":            _FIELD_LABELS[actual_field],
                    "configured_field": _FIELD_LABELS[configured_field],
                    "actual":           _extract_context(f[actual_field], kw),
                })
    return hits


def _matches_any_field(node: RequestNode, cfg: CustomFilterConfig) -> bool:
    return bool(_get_matches(node, cfg))


# ── any_field strategy ─────────────────────────────────────────────────────────

def _collect_all_descendants(node: RequestNode, match_info: list, reason: str = "ancestor_matched"):
    """Record every node in a subtree into match_info (preserved because an ancestor matched)."""
    match_info.append({
        "node_id":          node.id,
        "url":              node.url,
        "path":             node.path,
        "method":           node.method,
        "status":           node.status,
        "matches":          [],
        "preserved_reason": reason,
    })
    for child in node.children:
        _collect_all_descendants(child, match_info, "ancestor_matched")


def _filter_any_field(
    node: RequestNode,
    cfg: CustomFilterConfig,
    match_info: list,
) -> Optional[RequestNode]:
    hits = _get_matches(node, cfg)
    if hits:
        # This node matches — record it, then preserve ALL descendants unchanged.
        match_info.append({
            "node_id": node.id,
            "url":     node.url,
            "path":    node.path,
            "method":  node.method,
            "status":  node.status,
            "matches": hits,
        })
        for child in node.children:
            _collect_all_descendants(child, match_info, "ancestor_matched")
        # Return node with its full original subtree intact.
        return node

    # No match on this node — recurse into children.
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
            # Accept hits from any field: a keyword found via fallback in a
            # different field than configured still counts as matched.
            # field_filter is kept for AND-keyword-list mode (field_filter=None)
            # but for per-field keyword lists we accept any field match.
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

def _all_nodes(root: Optional[RequestNode], orphans: List[RequestNode]) -> List[RequestNode]:
    """Flat list of every node in the tree + orphans."""
    out: List[RequestNode] = []
    def _walk(n: RequestNode):
        out.append(n)
        for ch in n.children:
            _walk(ch)
    if root:
        _walk(root)
    out.extend(orphans)
    return out


def _match_combinations_in_tree(
    root: Optional[RequestNode],
    orphans: List[RequestNode],
    combinations: List[CombinationEntry],
) -> list:
    """
    For every CombinationEntry evaluate which keywords were found and in
    which nodes, then return rich per-keyword occurrence data.

    Strategy
    ────────
    1. Walk every node in the tree (including orphans) and record, for each
       (keyword, field_key) pair, ALL nodes where it appears — not just the
       first.  If "success" appears in 3 nodes we produce 3 occurrences.
    2. A keyword is "matched" if at least one occurrence exists.
    3. matched_keywords is a flat list of occurrences:
         {keyword, field, node_id, node_url, node_method, node_path}
       — one entry per occurrence so the UI can render a separate clickable
       chip for each node.
    4. If ALL configured keywords are matched (across any combination of
       nodes) → status="found" (global cross-branch match).
    5. Otherwise → partial or not_found as before.

    All text is sourced from _fields() which decodes headers, query params,
    and bodies before matching — keywords always hit decoded content.
    """
    if not combinations:
        return []

    all_nodes = _all_nodes(root, orphans)

    results = []

    for combo in combinations:
        # Collect the (cfg_field, field_key, keyword) triples we need to check
        kw_checks: list = []
        for cfg_field, field_key in _COMBO_FIELD_MAP:
            for kw_entry in getattr(combo, cfg_field, []):
                kw = kw_entry.strip() if isinstance(kw_entry, str) else str(kw_entry).strip()
                if kw:
                    kw_checks.append((cfg_field, field_key, kw))
        total_kws = len(kw_checks)
        if total_kws == 0:
            continue

        # For each (cfg_field, field_key, keyword) find ALL nodes that contain it.
        #
        # Search strategy — two-pass per keyword:
        #   Pass 1: look in the configured field_key (strict match).
        #   Pass 2: if not found in the designated field, search the "all" field
        #           as a fallback so that mis-filed keywords (e.g. SAMLRequest
        #           placed in res_header_keywords but actually present in the URL
        #           query params) are still matched and reported with the field
        #           where they were actually found.
        #
        # The occurrence key is (cfg_field, kw.lower()) — anchored to the
        # combination config field — so one keyword entry counts once even if
        # it appears in multiple actual fields.
        #
        # key: (cfg_field, kw.lower()) → list of node-occurrence dicts
        occurrences: dict = {}
        node_fields_cache: dict = {}  # node_id → _fields() result

        # All logical field keys in priority order for fallback reporting
        _ALL_FIELD_KEYS = ["url", "req_header", "res_header", "req_body", "res_body"]

        for node in all_nodes:
            if node.id not in node_fields_cache:
                node_fields_cache[node.id] = _fields(node)
            f = node_fields_cache[node.id]
            for _cfg_field, field_key, kw in kw_checks:
                occ_key = (_cfg_field, kw.lower())

                # Pass 1: check the designated field
                if _ci_contains(f[field_key], kw):
                    actual_field_label = _FIELD_LABELS[field_key]
                else:
                    # Pass 2: fallback — search every other field
                    actual_field_label = None
                    for fk in _ALL_FIELD_KEYS:
                        if fk != field_key and _ci_contains(f[fk], kw):
                            actual_field_label = _FIELD_LABELS[fk]
                            break

                if actual_field_label is not None:
                    if occ_key not in occurrences:
                        occurrences[occ_key] = []
                    occurrences[occ_key].append({
                        "keyword":         kw,
                        "field":           actual_field_label,
                        "configured_field": _FIELD_LABELS[field_key],
                        "node_id":         node.id,
                        "node_url":        node.url,
                        "node_method":     node.method,
                        "node_path":       node.path,
                    })

        # Build matched/unmatched lists
        matched_kws:   list = []
        unmatched_kws: list = []
        seen_unmatched: set = set()  # (cfg_field, kw.lower())

        for _cfg_field, field_key, kw in kw_checks:
            occ_key = (_cfg_field, kw.lower())
            occ = occurrences.get(occ_key, [])
            if occ:
                matched_kws.extend(occ)  # one entry per occurrence node
            else:
                if occ_key not in seen_unmatched:
                    seen_unmatched.add(occ_key)
                    unmatched_kws.append({
                        "keyword": kw,
                        "field":   _FIELD_LABELS[field_key],
                    })

        # Count distinct keywords that were found (not occurrences)
        found_distinct = len({(_cf, kw.lower()) for _cf, _fk, kw in kw_checks
                              if (_cf, kw.lower()) in occurrences})
        pct = round(found_distinct / total_kws * 100) if total_kws else 0

        if pct == 100:
            results.append({
                "name":               combo.name,
                "description":        combo.description or "",
                "status":             "found",
                "match_pct":          100,
                "total_keywords":     total_kws,
                "matched_keywords":   matched_kws,
                "unmatched_keywords": [],
                "matching_branches":  [],
                "global_match":       True,
            })
        elif pct > 0:
            results.append({
                "name":               combo.name,
                "description":        combo.description or "",
                "status":             "partial",
                "match_pct":          pct,
                "total_keywords":     total_kws,
                "matched_keywords":   matched_kws,
                "unmatched_keywords": unmatched_kws,
                "matching_branches":  [],
                "global_match":       False,
            })
        else:
            all_kw_labels = [
                {"keyword": kw, "field": _FIELD_LABELS[fk]}
                for _cf, fk, kw in kw_checks
            ]
            results.append({
                "name":               combo.name,
                "description":        combo.description or "",
                "status":             "not_found",
                "match_pct":          0,
                "total_keywords":     total_kws,
                "matched_keywords":   [],
                "unmatched_keywords": all_kw_labels,
                "matching_branches":  [],
                "global_match":       False,
            })

    return results


# ── Protocol score ─────────────────────────────────────────────────────────────

_SATURATION_TOP_N = 5


def _compute_overall_score(
    cfg: CustomFilterConfig,
    keyword_summary: dict,
    combination_results: list,
) -> dict:
    """
    Combined confidence score that blends keyword signals and combination results.

    Priority rules (from manager spec):
    ─────────────────────────────────────
    1. If ANY combination is 100% found → verdict = Confirmed (score = 100).
    2. If combinations exist (even partial):
         base_score = average of all combination match_pct values.
         If keywords are also present and matched, add keyword contribution:
           final = clamp(base + keyword_bonus, 0, 100)
         where keyword_bonus = kw_score * 0.4  (keywords are secondary).
    3. If only keywords, no combinations:
         pure keyword weighted-saturation score (original logic).
    4. If neither: score = 0.

    Score → Verdict:
      ≥ 70 → Confirmed | ≥ 40 → Likely | ≥ 15 → Possible | < 15 → Not detected
    """
    # ── Keyword component ─────────────────────────────────────────────────────
    all_weights: list = []
    earned: int       = 0
    evidence: list    = []

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

    top_n          = sorted(all_weights, reverse=True)[:_SATURATION_TOP_N]
    saturation     = sum(top_n) or 1
    total_weight   = sum(all_weights)
    kw_score       = min(100, round(earned / saturation * 100)) if all_weights else 0
    has_keywords   = bool(all_weights)
    evidence.sort(key=lambda x: x["weight"], reverse=True)

    # ── Combination component ─────────────────────────────────────────────────
    has_combos     = bool(combination_results)
    any_full       = any(r.get("status") == "found" for r in combination_results)
    combo_scores   = [r.get("match_pct", 0) for r in combination_results]
    avg_combo      = round(sum(combo_scores) / len(combo_scores)) if combo_scores else 0

    # Combination evidence for display
    combo_evidence = [
        {
            "combo_name": r.get("name", ""),
            "status":     r.get("status", "not_found"),
            "match_pct":  r.get("match_pct", 0),
        }
        for r in combination_results
    ]

    # ── Final score calculation ───────────────────────────────────────────────
    if any_full:
        # Any complete combination → maximum confidence
        final_score  = 100
        score_basis  = "combination_found"
    elif has_combos and has_keywords and earned > 0:
        # Both combinations and keywords matched — blend (combos primary 60%, kw 40%)
        keyword_bonus = kw_score * 0.4
        final_score   = min(100, round(avg_combo * 0.6 + keyword_bonus))
        score_basis   = "combined"
    elif has_combos:
        # Combinations present (with or without keyword config, or keywords present
        # but none matched) — combination score is the entire score
        final_score  = avg_combo
        score_basis  = "combinations_only"
    elif has_keywords:
        # Only keywords, no combinations configured
        final_score  = kw_score
        score_basis  = "keywords_only"
    else:
        final_score  = 0
        score_basis  = "none"

    verdict = (
        "Confirmed"    if final_score >= 70 else
        "Likely"       if final_score >= 40 else
        "Possible"     if final_score >= 15 else
        "Not detected"
    )

    return {
        "protocol":         cfg.name,
        "score":            final_score,
        "verdict":          verdict,
        "score_basis":      score_basis,
        # Keyword fields (for display)
        "earned":           earned,
        "saturation_point": saturation,
        "total_weight":     total_weight,
        "kw_score":         kw_score,
        "evidence":         evidence,
        # Combination fields (for display)
        "avg_combo_score":  avg_combo,
        "any_combo_found":  any_full,
        "combo_evidence":   combo_evidence,
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

    # ── Combination matching ── runs on the FILTERED tree/orphans so that
    # combinations only inspect nodes that survived keyword filtering.
    # When no keyword filter is configured (filtered_root == full root),
    # this is equivalent to running on the full tree.
    combination_results = _match_combinations_in_tree(
        filtered_root, filtered_orphans, cfg.combinations
    )

    protocol_score = _compute_overall_score(cfg, keyword_summary, combination_results)

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