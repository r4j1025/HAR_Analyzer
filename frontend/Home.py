"""
Home.py  —  HAR Tree Analyzer · Main page
"""
import json
import sys
import os

import streamlit as st

sys.path.insert(0, os.path.dirname(__file__))

from utils.api_client import APIClient
from utils.tree_renderer import render_tree_html

# ── Page config ───────────────────────────────────────────────────────────────

st.set_page_config(
    page_title="HAR Tree Analyzer",
    page_icon="🔍",
    layout="wide",
    initial_sidebar_state="expanded",
    menu_items={"About": "HAR Tree Analyzer v4 — API-first request flow explorer"},
)

# ── Session state defaults ────────────────────────────────────────────────────

_DEFAULTS = {
    "tree_data": None,
    "display_data": None,
    "filter_mode": "none",
    "custom_filter_config": None,
    "match_info": [],
    "keyword_summary": {},
    "protocol_score": None,
    "combination_results": [],
    "api_base_url": "http://localhost:8000",
    "last_error": None,
}
for k, v in _DEFAULTS.items():
    if k not in st.session_state:
        st.session_state[k] = v

# ── Custom CSS ────────────────────────────────────────────────────────────────

st.markdown("""
<style>
[data-testid="stSidebar"] { background: #0d1117; }
[data-testid="stSidebar"] * { color: #e6edf3 !important; }
[data-testid="stSidebar"] .stTextInput input,
[data-testid="stSidebar"] .stFileUploader { background: #161b22 !important; }
div[data-testid="metric-container"] { background: #161b22; border: 1px solid #30363d;
  border-radius: 8px; padding: 10px 14px; }
.filter-active-banner {
  background: linear-gradient(135deg,rgba(188,140,255,.12),rgba(188,140,255,.04));
  border: 1px solid rgba(188,140,255,.3); border-radius: 8px;
  padding: 8px 14px; font-size: 13px; margin-bottom: 8px; color: #e6edf3;
}

/* ── Keyword summary panel ── */
.kw-summary-header { font-size:13px;font-weight:700;color:#e6edf3;padding:6px 0 4px 0;letter-spacing:.01em; }
.kw-hit-row { background:#161b22;border:1px solid #30363d;border-radius:6px;padding:6px 12px;margin:4px 0;font-family:monospace;font-size:12px;line-height:1.6; }
.kw-method { color:#58a6ff;font-weight:700;margin-right:6px; }
.kw-path   { color:#e6edf3; }
.kw-field  { color:#8b949e;font-size:11px;margin-left:8px; }
.kw-actual { color:#d29922;font-size:11px;margin-top:2px; }
.kw-weight-badge { display:inline-block;background:#21262d;border:1px solid #30363d;border-radius:4px;padding:0 5px;font-size:10px;color:#8b949e;font-family:monospace;margin-left:6px;vertical-align:middle; }

/* ── Protocol verdict card ── */
.verdict-card { border-radius:10px;padding:16px 20px;margin:12px 0 4px 0;display:flex;align-items:center;gap:20px; }
.verdict-confirmed { background:rgba(63,185,80,.12); border:1px solid rgba(63,185,80,.4); }
.verdict-likely    { background:rgba(88,166,255,.10); border:1px solid rgba(88,166,255,.35); }
.verdict-possible  { background:rgba(210,153,34,.10); border:1px solid rgba(210,153,34,.35); }
.verdict-none      { background:rgba(139,148,158,.08);border:1px solid rgba(139,148,158,.3); }
.verdict-label { font-size:22px;font-weight:800;letter-spacing:.01em; }
.verdict-confirmed .verdict-label { color:#3fb950; }
.verdict-likely    .verdict-label { color:#58a6ff; }
.verdict-possible  .verdict-label { color:#d29922; }
.verdict-none      .verdict-label { color:#8b949e; }
.verdict-score-bar-wrap { flex:1;background:#21262d;border-radius:6px;height:10px;overflow:hidden; }
.verdict-score-bar { height:10px;border-radius:6px; }
.verdict-confirmed .verdict-score-bar { background:#3fb950; }
.verdict-likely    .verdict-score-bar { background:#58a6ff; }
.verdict-possible  .verdict-score-bar { background:#d29922; }
.verdict-none      .verdict-score-bar { background:#8b949e; }

/* ── Combination result cards ── */
.combo-result-card { border-radius:8px;padding:14px 16px;margin:6px 0; }
.combo-found   { background:rgba(63,185,80,.10); border:1px solid rgba(63,185,80,.35); }
.combo-partial { background:rgba(210,153,34,.10); border:1px solid rgba(210,153,34,.35); }
.combo-none    { background:rgba(139,148,158,.06);border:1px solid rgba(139,148,158,.25); }
.combo-pct-bar-wrap { background:#21262d;border-radius:4px;height:7px;overflow:hidden;margin:6px 0; }
.combo-pct-bar-found   { background:#3fb950;height:7px;border-radius:4px; }
.combo-pct-bar-partial { background:#d29922;height:7px;border-radius:4px; }
.combo-pct-bar-none    { background:#8b949e;height:7px;border-radius:4px; }
.combo-kw-found   { display:inline-flex;align-items:center;background:rgba(63,185,80,.12);border:1px solid rgba(63,185,80,.3);border-radius:4px;padding:1px 8px;font-size:11px;font-family:monospace;color:#3fb950;margin:2px; }
.combo-kw-missing { display:inline-flex;align-items:center;background:rgba(248,81,73,.08);border:1px solid rgba(248,81,73,.25);border-radius:4px;padding:1px 8px;font-size:11px;font-family:monospace;color:#f85149;margin:2px; }
.combo-branch-path { background:#161b22;border:1px solid #30363d;border-radius:5px;padding:6px 10px;font-family:monospace;font-size:11px;margin:4px 0;line-height:1.8; }
#decBreadcrumb { display:flex; }
</style>
""", unsafe_allow_html=True)


def get_client() -> APIClient:
    return APIClient(st.session_state.api_base_url)


# ── Protocol verdict renderer ─────────────────────────────────────────────────

def _render_protocol_verdict(ps: dict):
    verdict       = ps.get("verdict", "Not detected")
    score         = ps.get("score", 0)
    protocol      = ps.get("protocol", "Protocol")
    earned        = ps.get("earned", 0)
    sat           = ps.get("saturation_point", 0)
    total_w       = ps.get("total_weight", 0)
    kw_score      = ps.get("kw_score", 0)
    evidence      = ps.get("evidence", [])
    score_basis   = ps.get("score_basis", "keywords_only")
    avg_combo     = ps.get("avg_combo_score", 0)
    any_full      = ps.get("any_combo_found", False)
    combo_ev      = ps.get("combo_evidence", [])

    verdict_class = {
        "Confirmed":    "verdict-confirmed",
        "Likely":       "verdict-likely",
        "Possible":     "verdict-possible",
        "Not detected": "verdict-none",
    }.get(verdict, "verdict-none")

    verdict_icon = {
        "Confirmed":    "✅",
        "Likely":       "🔵",
        "Possible":     "🟡",
        "Not detected": "❌",
    }.get(verdict, "❔")

    # Build score breakdown subtitle
    basis_map = {
        "combination_found": "Combination fully matched → Confirmed",
        "combined":          f"Combinations avg {avg_combo}% · Keywords {kw_score}/100 (blended)",
        "combinations_only": f"Combinations avg {avg_combo}% (no keywords configured)",
        "keywords_only":     f"Keywords: {earned}/{sat} pts (top-5 threshold)",
        "none":              "No keywords or combinations configured",
    }
    basis_label = basis_map.get(score_basis, "")

    # Top keyword signals
    top_ev = evidence[:3]
    ev_chips_parts = []
    for e in top_ev:
        ev_chips_parts.append(
            f'<code style="background:#1c2128;border:1px solid #30363d;border-radius:4px;'
            f'padding:1px 6px;font-size:11px;color:#e6edf3">'
            f'{e["keyword"]} <span style="color:#d29922">w{e["weight"]}</span></code>'
        )
    ev_chips = " &nbsp;".join(ev_chips_parts)

    # Combo pills
    combo_pills = ""
    if combo_ev:
        pills = []
        for ce in combo_ev[:4]:
            pct  = ce["match_pct"]
            col  = "#3fb950" if pct==100 else "#d29922" if pct>0 else "#8b949e"
            pills.append(
                f'<span style="background:#21262d;border:1px solid {col};border-radius:4px;'
                f'padding:1px 8px;font-size:10px;color:{col};font-family:monospace;margin:2px">'
                f'{ce["combo_name"][:20]} {pct}%</span>'
            )
        combo_pills = '<div style="margin-top:6px;flex-wrap:wrap;display:flex;gap:3px">' + "".join(pills) + '</div>'

    if top_ev:
        top_signals_html = '<div style="margin-top:5px;font-size:11px;color:#8b949e">Top signals: ' + ev_chips + '</div>'
    else:
        top_signals_html = ""

    st.markdown(
        f'<div class="verdict-card {verdict_class}">'
        f'  <div style="min-width:200px">'
        f'    <div style="font-size:11px;color:#8b949e;margin-bottom:2px;text-transform:uppercase;letter-spacing:.06em">Protocol Detection</div>'
        f'    <div style="font-size:14px;font-weight:700;color:#e6edf3">{protocol}</div>'
        f'  </div>'
        f'  <div style="flex:1">'
        f'    <div style="display:flex;align-items:center;gap:10px;margin-bottom:6px">'
        f'      <span class="verdict-label">{verdict_icon} {verdict}</span>'
        f'      <span style="color:#8b949e;font-size:13px">{score}/100</span>'
        f'    </div>'
        f'    <div class="verdict-score-bar-wrap">'
        f'      <div class="verdict-score-bar" style="width:{score}%"></div>'
        f'    </div>'
        f'    <div style="font-size:11px;color:#8b949e;margin-top:5px">{basis_label}</div>'
        f'    {combo_pills}'
        f'    {top_signals_html}'
        f'  </div>'
        f'</div>',
        unsafe_allow_html=True,
    )


# ── Combination results renderer ──────────────────────────────────────────────

def _render_combination_results(combination_results: list):
    """
    Render combination results summary cards above the tree.

    The interactive keyword hit buttons (one per occurrence per node) live
    inside the tree iframe's combo panel — rendered by renderComboPanel() in
    tree_renderer.py using COMBO_INFO injected at render time.  Clicking any
    button there calls jumpToNode() directly, opening the node and highlighting
    all matched keywords.

    This function shows only the status summary cards so the user can see the
    overall verdict before scrolling to the tree.
    """
    if not combination_results:
        return

    st.markdown("---")
    found_n   = sum(1 for r in combination_results if r["status"] == "found")
    partial_n = sum(1 for r in combination_results if r["status"] == "partial")
    total_n   = len(combination_results)

    st.markdown(
        f"### 🔗 Combination Results &nbsp;"
        f"<span style='font-size:14px;font-family:monospace;color:#bc8cff'>"
        f"{found_n} found · {partial_n} partial · {total_n - found_n - partial_n} not found"
        f"</span>",
        unsafe_allow_html=True,
    )

    for result in combination_results:
        name        = result.get("name", "Unnamed")
        description = result.get("description", "")
        status      = result.get("status", "not_found")
        pct         = result.get("match_pct", 0)
        matched_kws = result.get("matched_keywords", [])
        missing_kws = result.get("unmatched_keywords", [])
        total_kws   = result.get("total_keywords", 0)

        if status == "found":
            card_cls = "combo-found"
            bar_cls  = "combo-pct-bar-found"
            icon     = "✅"
            label    = "Found (100%)"
        elif status == "partial":
            card_cls = "combo-partial"
            bar_cls  = "combo-pct-bar-partial"
            icon     = "⚡"
            distinct = len({m["keyword"].lower() for m in matched_kws})
            label    = f"Partial — {pct}%  ({distinct}/{total_kws} keywords)"
        else:
            card_cls = "combo-none"
            bar_cls  = "combo-pct-bar-none"
            icon     = "❌"
            label    = "Not Found"

        expanded = status in ("found", "partial")

        with st.expander(f"{icon} **{name}** — {label}", expanded=expanded):
            if description:
                st.caption(description)

            # Progress bar
            st.markdown(
                f'<div class="combo-pct-bar-wrap">'
                f'<div class="{bar_cls}" style="width:{pct}%"></div></div>',
                unsafe_allow_html=True,
            )

            # Keyword status chips (static — just show ✓/✗, no clicks needed here)
            # The clickable occurrence buttons are in the combo panel inside the tree.
            kw_html = ""
            seen = set()
            for kw in matched_kws:
                key = kw["keyword"].lower()
                if key not in seen:
                    seen.add(key)
                    occ = sum(1 for m in matched_kws if m["keyword"].lower() == key)
                    occ_note = f' <span style="opacity:.5;font-size:9px">×{occ}</span>' if occ > 1 else ""
                    kw_html += (
                        f'<span class="combo-kw-found">✓ {kw["keyword"]}{occ_note}'
                        f'<span style="opacity:.6;margin-left:4px;font-size:10px">'
                        f'in {kw["field"]}</span></span>'
                    )
            for kw in missing_kws:
                kw_html += (
                    f'<span class="combo-kw-missing">✗ {kw["keyword"]}'
                    f'<span style="opacity:.6;margin-left:4px;font-size:10px">'
                    f'in {kw["field"]}</span></span>'
                )
            if kw_html:
                st.markdown(
                    f'<div style="margin:8px 0;line-height:2.2">{kw_html}</div>',
                    unsafe_allow_html=True,
                )

            if status in ("found", "partial") and matched_kws:
                st.caption("↓ Click keyword buttons in the 🔗 Combination Keywords panel below the tree to jump to each node")


# ── Keyword summary renderer ──────────────────────────────────────────────────

def _render_keyword_summary(keyword_summary: dict):
    _CAT_ICONS = {
        "URL Keywords":             "🌐",
        "Request Header Keywords":  "📤",
        "Response Header Keywords": "📥",
        "Request Body Keywords":    "📦",
        "Response Body Keywords":   "📨",
        "AND Keyword List":         "🔗",
    }

    total_kw      = sum(len(v) for v in keyword_summary.values())
    total_matched = sum(
        sum(1 for e in v if e["matched"])
        for v in keyword_summary.values()
    )

    st.markdown("---")
    st.markdown(
        f"### 🔑 Keyword Match Summary &nbsp; "
        f"<span style='font-size:14px;color:#bc8cff;font-family:monospace'>"
        f"{total_matched}/{total_kw} keywords identified</span>",
        unsafe_allow_html=True,
    )

    for category, entries in keyword_summary.items():
        matched_count = sum(1 for e in entries if e["matched"])
        total_in_cat  = len(entries)
        icon          = _CAT_ICONS.get(category, "🔑")

        with st.expander(
            f"{icon} {category} — {matched_count}/{total_in_cat} matched",
            expanded=(matched_count > 0),
        ):
            rows_html = ""
            for entry in entries:
                kw      = entry["keyword"]
                weight  = entry.get("weight", 5)
                matched = entry["matched"]
                hits    = entry.get("hits", [])
                w_badge = f'<span class="kw-weight-badge">w{weight}</span>'

                if matched and hits:
                    unique_nodes = len({h["node_id"] for h in hits})
                    rows_html += (
                        f'<div style="display:flex;align-items:center;gap:8px;'
                        f'padding:5px 0 3px 0;border-top:1px solid #21262d;">'
                        f'<span style="font-size:15px">✅</span>'
                        f'<code style="background:#1c2128;border:1px solid #30363d;'
                        f'border-radius:4px;padding:1px 7px;font-size:12px;color:#e6edf3">'
                        f'{kw}</code>{w_badge}'
                        f'<span style="color:#8b949e;font-size:11px;margin-left:4px">'
                        f'→ {unique_nodes} node(s), {len(hits)} hit(s)</span>'
                        f'</div>'
                    )
                    for h in hits:
                        mc = {
                            "GET":"#3fb950","POST":"#58a6ff","PUT":"#d29922",
                            "DELETE":"#f85149","PATCH":"#bc8cff",
                        }.get(h["method"], "#8b949e")
                        rows_html += (
                            f'<div style="margin:3px 0 3px 28px;background:#161b22;'
                            f'border:1px solid #30363d;border-radius:5px;'
                            f'padding:5px 10px;font-family:monospace;font-size:12px;line-height:1.6">'
                            f'<span style="color:{mc};font-weight:700;margin-right:6px">{h["method"]}</span>'
                            f'<span style="color:#e6edf3">{h["path"]}</span>'
                            f'<span style="color:#8b949e;font-size:11px;margin-left:8px">in {h["field"]}</span>'
                            f'<div style="color:#d29922;font-size:11px;margin-top:2px">↳ {h["actual"]}</div>'
                            f'</div>'
                        )
                else:
                    rows_html += (
                        f'<div style="display:flex;align-items:center;gap:8px;'
                        f'padding:5px 0 3px 0;border-top:1px solid #21262d;">'
                        f'<span style="font-size:15px">❌</span>'
                        f'<code style="background:#161b22;border:1px solid #21262d;'
                        f'border-radius:4px;padding:1px 7px;font-size:12px;color:#8b949e">'
                        f'{kw}</code>{w_badge}'
                        f'</div>'
                    )

            st.markdown(
                f'<div style="padding:4px 0 8px 0">{rows_html}</div>',
                unsafe_allow_html=True,
            )


# ── Sidebar ───────────────────────────────────────────────────────────────────

with st.sidebar:
    st.markdown("## ⚙️ API")
    api_url = st.text_input(
        "Backend URL",
        value=st.session_state.api_base_url,
        label_visibility="collapsed",
        placeholder="http://localhost:8000",
    )
    if api_url != st.session_state.api_base_url:
        st.session_state.api_base_url = api_url

    try:
        get_client().health()
        st.caption("🟢 Backend connected")
    except Exception:
        st.caption("🔴 Backend unreachable — start it first")

    st.divider()
    st.markdown("## 📂 Upload")

    root_url = st.text_input(
        "Root URL",
        placeholder="https://app.example.com",
        help="The page URL where you started recording the HAR",
    )

    har_files = st.file_uploader(
        "HAR Files",
        type=["har"],
        accept_multiple_files=True,
        help="Drop one or more .har files exported from browser DevTools",
    )

    analyze_disabled = not (root_url and har_files)

    if st.button("🔍 Analyze", type="primary", use_container_width=True,
                 disabled=analyze_disabled):
        with st.spinner("Parsing HAR files and building tree…"):
            try:
                result = get_client().analyze(root_url, har_files)
                st.session_state.tree_data           = result
                st.session_state.display_data        = result
                st.session_state.filter_mode         = "none"
                st.session_state.custom_filter_config= None
                st.session_state.match_info          = []
                st.session_state.keyword_summary     = {}
                st.session_state.protocol_score      = None
                st.session_state.combination_results = []
                st.session_state.last_error          = None
                st.success(f"✅ {len(har_files)} file(s) analyzed")
                st.rerun()
            except Exception as e:
                st.session_state.last_error = str(e)
                st.error(str(e))

    if st.session_state.tree_data:
        data    = st.session_state.tree_data
        summary = data.get("summary", {})
        st.divider()
        st.markdown("## 📊 Stats")
        c1, c2 = st.columns(2)
        c1.metric("Tree nodes",   summary.get("total_nodes_in_tree", 0))
        c2.metric("Noise removed",data.get("noise_removed", 0))
        c1.metric("Max depth",    summary.get("max_tree_depth", 0))
        c2.metric("Orphans",      len(data.get("orphan_nodes", [])))
        st.divider()
        st.markdown("**By method**")
        for method, cnt in summary.get("by_method", {}).items():
            st.caption(f"{method}: {cnt}")
        st.markdown("**By status**")
        for status, cnt in summary.get("by_status_class", {}).items():
            st.caption(f"{status}: {cnt}")
        st.divider()
        st.download_button(
            "⬇ Download Tree JSON",
            data=json.dumps(st.session_state.tree_data, indent=2),
            file_name="har_tree.json",
            mime="application/json",
            use_container_width=True,
        )


# ── Main area ─────────────────────────────────────────────────────────────────

st.markdown("# 🔍 HAR Tree Analyzer")

if st.session_state.last_error:
    st.error(st.session_state.last_error)

if not st.session_state.tree_data:
    st.markdown("""
    <div style="text-align:center;padding:80px 20px;color:#8b949e">
      <div style="font-size:56px;margin-bottom:16px">🗂️</div>
      <h2 style="color:#e6edf3;font-weight:600;margin-bottom:8px">Upload HAR files to get started</h2>
      <p>Use the sidebar to upload one or more <code>.har</code> files exported from browser DevTools.</p>
    </div>
    """, unsafe_allow_html=True)
    st.stop()

# ── Filter bar ────────────────────────────────────────────────────────────────

fc1, fc2, fc3 = st.columns([2, 2, 8])

with fc1:
    if st.button("🌐 Show All", use_container_width=True):
        st.session_state.display_data        = st.session_state.tree_data
        st.session_state.filter_mode         = "none"
        st.session_state.custom_filter_config= None
        st.session_state.match_info          = []
        st.session_state.keyword_summary     = {}
        st.session_state.protocol_score      = None
        st.session_state.combination_results = []
        st.rerun()

with fc2:
    custom_active = st.session_state.filter_mode == "custom"
    if st.button("🎯 Filter / Search", use_container_width=True,
                 type="primary" if custom_active else "secondary"):
        st.switch_page("pages/Custom_Filter.py")

# ── Active filter banner ──────────────────────────────────────────────────────

display = st.session_state.display_data or st.session_state.tree_data
mode    = st.session_state.filter_mode

if mode == "custom" and st.session_state.custom_filter_config:
    cfg         = st.session_state.custom_filter_config
    total       = display.get("total_custom_nodes", 0)
    name        = cfg.get("name", "Custom")
    match_mode  = cfg.get("match_mode", "any_field")
    mode_label  = "AND list" if match_mode == "keyword_list" else "field keywords"
    match_count = len(st.session_state.match_info)
    n_combos    = len(cfg.get("combinations", []))
    combo_found = sum(
        1 for r in st.session_state.combination_results if r.get("status") == "found"
    )
    combo_hint  = f" · 🔗 {combo_found}/{n_combos} combinations" if n_combos else ""

    col_a, col_b = st.columns([8, 1])
    col_a.markdown(
        f'<div class="filter-active-banner">'
        f'🎯 <strong>{name}</strong> ({mode_label}) — {total} matching nodes'
        f' · <span style="color:#bc8cff">{match_count} keyword hits</span>'
        f'{combo_hint}'
        f'</div>',
        unsafe_allow_html=True,
    )
    if col_b.button("✕ Clear"):
        st.session_state.display_data        = st.session_state.tree_data
        st.session_state.filter_mode         = "none"
        st.session_state.custom_filter_config= None
        st.session_state.match_info          = []
        st.session_state.keyword_summary     = {}
        st.session_state.protocol_score      = None
        st.session_state.combination_results = []
        st.rerun()

# ── Download filtered JSON ────────────────────────────────────────────────────

if mode != "none":
    st.download_button(
        "⬇ Download Filtered JSON",
        data=json.dumps(display, indent=2),
        file_name="har_tree_filtered.json",
        mime="application/json",
    )

# ── Tree component ────────────────────────────────────────────────────────────

tree_html = render_tree_html(
    display,
    filter_mode=mode,
    match_info=st.session_state.match_info,
    combination_results=st.session_state.get("combination_results", []),
    height=800,
)
st.components.v1.html(tree_html, height=800, scrolling=False)

# ── Results panels ────────────────────────────────────────────────────────────

protocol_score:     dict  = st.session_state.get("protocol_score") or {}
keyword_summary:    dict  = st.session_state.get("keyword_summary", {})
combination_results: list = st.session_state.get("combination_results", [])

if mode == "custom" and protocol_score:
    _render_protocol_verdict(protocol_score)

if mode == "custom" and combination_results:
    _render_combination_results(combination_results)

if mode == "custom" and keyword_summary:
    _render_keyword_summary(keyword_summary)

# ── Debug info ────────────────────────────────────────────────────────────────

summary      = st.session_state.tree_data.get("summary", {})
tree_nodes   = summary.get("total_nodes_in_tree", 0)
orphan_count = len(st.session_state.tree_data.get("orphan_nodes", []))

if tree_nodes == 0 and orphan_count == 0:
    st.warning(
        "⚠ The tree has 0 nodes. This usually means the **Root URL domain** "
        "doesn't match entries in the HAR file. Check the debug panel below."
    )

with st.expander("🐛 Debug — raw API response summary", expanded=(tree_nodes == 0)):
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Tree nodes",         tree_nodes)
    col2.metric("Orphan nodes",       orphan_count)
    col3.metric("Raw HAR entries",    st.session_state.tree_data.get("total_entries_raw","?"))
    col4.metric("After noise filter", st.session_state.tree_data.get("total_entries_filtered","?"))
    st.caption(f"Root URL: `{st.session_state.tree_data.get('root_url','')}`")
    st.caption(f"HAR files: {st.session_state.tree_data.get('har_files',[])}")
    if summary.get("by_method"):
        st.caption(f"Methods: {summary['by_method']}")
    if summary.get("by_status_class"):
        st.caption(f"Statuses: {summary['by_status_class']}")