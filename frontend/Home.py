"""
Home.py  —  HAR Tree Analyzer · Main page
──────────────────────────────────────────
Upload HAR files, build the full request/response tree, then optionally apply
a custom filter.

Changes from v3:
  - Auth Filter button removed entirely.
  - default_filter.json loading removed.
  - Keyword summary panel: shows ALL keywords from the active filter config,
    each with ✅ (matched) or ❌ (not found), and expandable hit details below
    every matched keyword.
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
    "filter_mode": "none",        # "none" | "custom"
    "custom_filter_config": None,
    "match_info": [],             # list of match records from last filter
    "keyword_summary": {},        # {category: [{keyword, weight, matched, hits}]}
    "protocol_score": None,       # weighted scoring result from last filter
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
.kw-summary-header {
  font-size: 13px; font-weight: 700; color: #e6edf3;
  padding: 6px 0 4px 0; letter-spacing: .01em;
}
.kw-hit-row {
  background: #161b22; border: 1px solid #30363d; border-radius: 6px;
  padding: 6px 12px; margin: 4px 0; font-family: monospace; font-size: 12px;
  line-height: 1.6;
}
.kw-method { color: #58a6ff; font-weight: 700; margin-right: 6px; }
.kw-path   { color: #e6edf3; }
.kw-field  { color: #8b949e; font-size: 11px; margin-left: 8px; }
.kw-actual { color: #d29922; font-size: 11px; margin-top: 2px; }

/* ── Protocol verdict card ── */
.verdict-card {
  border-radius: 10px; padding: 16px 20px; margin: 12px 0 4px 0;
  display: flex; align-items: center; gap: 20px;
}
.verdict-confirmed { background: rgba(63,185,80,.12);  border: 1px solid rgba(63,185,80,.4); }
.verdict-likely     { background: rgba(88,166,255,.10); border: 1px solid rgba(88,166,255,.35); }
.verdict-possible   { background: rgba(210,153,34,.10); border: 1px solid rgba(210,153,34,.35); }
.verdict-none       { background: rgba(139,148,158,.08);border: 1px solid rgba(139,148,158,.3); }
.verdict-label { font-size: 22px; font-weight: 800; letter-spacing: .01em; }
.verdict-confirmed .verdict-label { color: #3fb950; }
.verdict-likely     .verdict-label { color: #58a6ff; }
.verdict-possible   .verdict-label { color: #d29922; }
.verdict-none       .verdict-label { color: #8b949e; }
.verdict-score-bar-wrap {
  flex: 1; background: #21262d; border-radius: 6px; height: 10px; overflow: hidden;
}
.verdict-score-bar { height: 10px; border-radius: 6px; transition: width .4s; }
.verdict-confirmed .verdict-score-bar { background: #3fb950; }
.verdict-likely     .verdict-score-bar { background: #58a6ff; }
.verdict-possible   .verdict-score-bar { background: #d29922; }
.verdict-none       .verdict-score-bar { background: #8b949e; }
.kw-weight-badge {
  display:inline-block; background:#21262d; border:1px solid #30363d;
  border-radius:4px; padding:0 5px; font-size:10px; color:#8b949e;
  font-family:monospace; margin-left:6px; vertical-align:middle;
}
</style>
""", unsafe_allow_html=True)


def get_client() -> APIClient:
    return APIClient(st.session_state.api_base_url)


# ── Protocol verdict renderer ─────────────────────────────────────────────────

def _render_protocol_verdict(ps: dict):
    """
    Render a verdict card at the top of the results section.

    Layout:
      ┌─────────────────────────────────────────────────────────────────────┐
      │  🔐 SAML Filter          Confirmed ████████████░░░  87 / 100        │
      │  Matched 12 keywords · top signals: SAMLResponse(10) saml:Assertion │
      └─────────────────────────────────────────────────────────────────────┘
    """
    verdict   = ps.get("verdict", "Not detected")
    score     = ps.get("score", 0)
    protocol  = ps.get("protocol", "Protocol")
    earned           = ps.get("earned", 0)
    saturation_point  = ps.get("saturation_point", 0)
    total_weight      = ps.get("total_weight", 0)
    evidence  = ps.get("evidence", [])

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

    # Top-3 evidence snippets
    top_evidence = evidence[:3]
    evidence_chips = " &nbsp;".join(
        f'<code style="background:#1c2128;border:1px solid #30363d;border-radius:4px;'
        f'padding:1px 6px;font-size:11px;color:#e6edf3">'
        f'{e["keyword"]} <span style="color:#d29922">w{e["weight"]}</span></code>'
        for e in top_evidence
    )
    matched_count = len(evidence)

    # Pre-compute optional line to avoid backslash inside f-string (Python < 3.12)
    if top_evidence:
        top_signals_html = '<div style="margin-top:6px">Top signals: ' + evidence_chips + '</div>'
    else:
        top_signals_html = ''

    st.markdown(
        f'<div class="verdict-card {verdict_class}">'
        f'  <div style="min-width:180px">'
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
        f'    <div style="font-size:11px;color:#8b949e;margin-top:6px">'
        f'      Confidence: {earned} pts earned · threshold {saturation_point} pts (top-5 signals) · {total_weight} pts total'
        f'    </div>'
        f'    {top_signals_html}'
        f'  </div>'
        f'</div>',
        unsafe_allow_html=True,
    )


# ── Keyword summary renderer ──────────────────────────────────────────────────

def _render_keyword_summary(keyword_summary: dict):
    """
    Render a full keyword match summary below the tree.

    Layout (one expander per category — NO nesting, Streamlit limitation):
      ┌─ 🌐 URL Keywords — 3/12 matched ──────────────────── [expander] ─┐
      │  ✅  /oauth  →  2 node(s), 4 hit(s)                              │
      │     ┌──────────────────────────────────────────────────────────┐  │
      │     │ GET  /oauth/token   in URL   ↳ …/oauth/token?client…    │  │
      │     └──────────────────────────────────────────────────────────┘  │
      │  ❌  /authorize                                                   │
      └────────────────────────────────────────────────────────────────────┘
    """
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

        # ONE expander per category — hits are rendered as plain HTML inside,
        # no nested expanders (Streamlit forbids them).
        with st.expander(
            f"{icon} {category} — {matched_count}/{total_in_cat} matched",
            expanded=(matched_count > 0),
        ):
            # Build the entire category body as a single HTML block so we
            # never call st.expander() again inside this context.
            rows_html = ""
            for entry in entries:
                kw      = entry["keyword"]
                weight  = entry.get("weight", 5)
                matched = entry["matched"]
                hits    = entry.get("hits", [])
                w_badge = f'<span class="kw-weight-badge">w{weight}</span>'

                if matched and hits:
                    unique_nodes = len({h["node_id"] for h in hits})

                    # ── Matched keyword header row ──
                    rows_html += (
                        f'<div style="display:flex;align-items:center;gap:8px;'
                        f'padding:5px 0 3px 0;border-top:1px solid #21262d;">'
                        f'<span style="font-size:15px">✅</span>'
                        f'<code style="background:#1c2128;border:1px solid #30363d;'
                        f'border-radius:4px;padding:1px 7px;font-size:12px;color:#e6edf3">'
                        f'{kw}</code>'
                        f'{w_badge}'
                        f'<span style="color:#8b949e;font-size:11px;margin-left:4px">'
                        f'→ {unique_nodes} node(s), {len(hits)} hit(s)</span>'
                        f'</div>'
                    )

                    # ── Hit detail rows (indented) ──
                    for h in hits:
                        method_color = {
                            "GET":    "#3fb950", "POST":   "#58a6ff",
                            "PUT":    "#d29922", "DELETE": "#f85149",
                            "PATCH":  "#bc8cff",
                        }.get(h["method"], "#8b949e")

                        rows_html += (
                            f'<div style="margin:3px 0 3px 28px;background:#161b22;'
                            f'border:1px solid #30363d;border-radius:5px;'
                            f'padding:5px 10px;font-family:monospace;font-size:12px;'
                            f'line-height:1.6">'
                            f'<span style="color:{method_color};font-weight:700;'
                            f'margin-right:6px">{h["method"]}</span>'
                            f'<span style="color:#e6edf3">{h["path"]}</span>'
                            f'<span style="color:#8b949e;font-size:11px;margin-left:8px">'
                            f'in {h["field"]}</span>'
                            f'<div style="color:#d29922;font-size:11px;margin-top:2px">'
                            f'↳ {h["actual"]}</div>'
                            f'</div>'
                        )

                else:
                    # ── Unmatched keyword ──
                    rows_html += (
                        f'<div style="display:flex;align-items:center;gap:8px;'
                        f'padding:5px 0 3px 0;border-top:1px solid #21262d;">'
                        f'<span style="font-size:15px">❌</span>'
                        f'<code style="background:#161b22;border:1px solid #21262d;'
                        f'border-radius:4px;padding:1px 7px;font-size:12px;color:#8b949e">'
                        f'{kw}</code>'
                        f'{w_badge}'
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

    if st.button(
        "🔍 Analyze",
        type="primary",
        use_container_width=True,
        disabled=analyze_disabled,
    ):
        with st.spinner("Parsing HAR files and building tree…"):
            try:
                result = get_client().analyze(root_url, har_files)
                st.session_state.tree_data = result
                st.session_state.display_data = result
                st.session_state.filter_mode = "none"
                st.session_state.custom_filter_config = None
                st.session_state.match_info = []
                st.session_state.keyword_summary = {}
                st.session_state.last_error = None
                st.success(f"✅ {len(har_files)} file(s) analyzed")
                st.rerun()
            except Exception as e:
                st.session_state.last_error = str(e)
                st.error(str(e))

    # ── Stats ─────────────────────────────────────────────────────────────────
    if st.session_state.tree_data:
        data = st.session_state.tree_data
        summary = data.get("summary", {})
        st.divider()
        st.markdown("## 📊 Stats")

        c1, c2 = st.columns(2)
        c1.metric("Tree nodes", summary.get("total_nodes_in_tree", 0))
        c2.metric("Noise removed", data.get("noise_removed", 0))
        c1.metric("Max depth", summary.get("max_tree_depth", 0))
        c2.metric("Orphans", len(data.get("orphan_nodes", [])))

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
      <p style="margin-top:8px">Use the Custom Filter button to focus on specific flows.</p>
    </div>
    """, unsafe_allow_html=True)
    st.stop()

# ── Filter bar ────────────────────────────────────────────────────────────────

fc1, fc2, fc3 = st.columns([2, 2, 8])

with fc1:
    if st.button("🌐 Show All", use_container_width=True):
        st.session_state.display_data = st.session_state.tree_data
        st.session_state.filter_mode = "none"
        st.session_state.custom_filter_config = None
        st.session_state.match_info = []
        st.session_state.keyword_summary = {}
        st.session_state.protocol_score = None
        st.rerun()

with fc2:
    custom_active = st.session_state.filter_mode == "custom"
    if st.button(
        "🎯 Custom Filter",
        use_container_width=True,
        type="primary" if custom_active else "secondary",
    ):
        st.switch_page("pages/Custom_Filter.py")

# ── Active filter banner ──────────────────────────────────────────────────────

display = st.session_state.display_data or st.session_state.tree_data
mode = st.session_state.filter_mode

if mode == "custom" and st.session_state.custom_filter_config:
    cfg = st.session_state.custom_filter_config
    total = display.get("total_custom_nodes", 0)
    name = cfg.get("name", "Custom")
    match_mode = cfg.get("match_mode", "any_field")
    mode_label = "AND list" if match_mode == "keyword_list" else "field keywords"
    match_count = len(st.session_state.match_info)
    col_a, col_b = st.columns([8, 1])
    col_a.markdown(
        f'<div class="filter-active-banner">'
        f'🎯 <strong>{name}</strong> ({mode_label}) — {total} matching nodes'
        f' · <span style="color:#bc8cff">{match_count} keyword hits</span>'
        f'</div>',
        unsafe_allow_html=True,
    )
    if col_b.button("✕ Clear"):
        st.session_state.display_data = st.session_state.tree_data
        st.session_state.filter_mode = "none"
        st.session_state.custom_filter_config = None
        st.session_state.match_info = []
        st.session_state.keyword_summary = {}
        st.session_state.protocol_score = None
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
    height=800,
)
st.components.v1.html(tree_html, height=800, scrolling=False)

# ── Keyword summary panel ─────────────────────────────────────────────────────

keyword_summary: dict = st.session_state.get("keyword_summary", {})
protocol_score:  dict = st.session_state.get("protocol_score") or {}

if mode == "custom" and protocol_score:
    _render_protocol_verdict(protocol_score)

if mode == "custom" and keyword_summary:
    _render_keyword_summary(keyword_summary)

# ── Debug info ────────────────────────────────────────────────────────────────

summary = st.session_state.tree_data.get("summary", {})
tree_nodes = summary.get("total_nodes_in_tree", 0)
orphan_count = len(st.session_state.tree_data.get("orphan_nodes", []))

if tree_nodes == 0 and orphan_count == 0:
    st.warning(
        "⚠ The tree has 0 nodes. This usually means the **Root URL domain** "
        "doesn't match entries in the HAR file. "
        "Check the debug panel below."
    )

with st.expander("🐛 Debug — raw API response summary", expanded=(tree_nodes == 0)):
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Tree nodes", tree_nodes)
    col2.metric("Orphan nodes", orphan_count)
    col3.metric("Raw HAR entries", st.session_state.tree_data.get("total_entries_raw", "?"))
    col4.metric("After noise filter", st.session_state.tree_data.get("total_entries_filtered", "?"))
    st.caption(f"Root URL stored in tree: `{st.session_state.tree_data.get('root_url','')}`")
    st.caption(f"HAR files: {st.session_state.tree_data.get('har_files', [])}")
    if summary.get("by_method"):
        st.caption(f"Methods: {summary['by_method']}")
    if summary.get("by_status_class"):
        st.caption(f"Statuses: {summary['by_status_class']}")