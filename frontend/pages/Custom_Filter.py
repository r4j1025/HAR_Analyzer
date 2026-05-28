"""
pages/Custom_Filter.py  -  HAR Tree Analyzer - Custom Filter Config
"""
import json, sys, os
import streamlit as st

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from utils.api_client import APIClient

st.set_page_config(page_title="Custom Filter", page_icon="🎯",
                   layout="wide", initial_sidebar_state="collapsed")

st.markdown("""<style>
.kw-chip{display:inline-flex;align-items:center;gap:6px;background:#1c2128;
  border:1px solid #30363d;border-radius:16px;padding:3px 10px;font-size:12px;
  font-family:monospace;color:#e6edf3;margin:3px 3px 3px 0}
.schema-error{background:rgba(248,81,73,.1);border:1px solid rgba(248,81,73,.4);
  border-radius:8px;padding:10px 14px;color:#f85149;font-size:13px}
.cfg-ok{background:rgba(63,185,80,.1);border:1px solid rgba(63,185,80,.4);
  border-radius:8px;padding:10px 14px;color:#3fb950;font-size:13px}
.combo-card{background:#161b22;border:1px solid #30363d;border-radius:8px;padding:12px 16px;margin:6px 0}
</style>""", unsafe_allow_html=True)


# ── Session state defaults ────────────────────────────────────────────────────

def _init():
    defaults = {
        "cf": {
            "version": "1.0", "name": "My Custom Filter", "description": "",
            "url_keywords": [], "req_header_keywords": [], "res_header_keywords": [],
            "req_body_keywords": [], "res_body_keywords": [],
            "keyword_list": [], "match_mode": "any_field",
            "combinations": [],
        },
        "match_info": [],
        "keyword_summary": {},
        "protocol_score": None,
        "combination_results": [],
        "_last_cfg_file_id": None,
        "_mode_radio": "any_field",
        "_cfg_load_msg": None,
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v
    # Ensure combinations key exists on older session states
    st.session_state.cf.setdefault("combinations", [])

_init()


def _client():
    return APIClient(st.session_state.get("api_base_url", "http://localhost:8000"))


# ── Keyword entry helpers ─────────────────────────────────────────────────────

def _kw_str(entry) -> str:
    return entry["keyword"] if isinstance(entry, dict) else str(entry)

def _kw_weight(entry) -> int:
    return int(entry.get("weight", 5)) if isinstance(entry, dict) else 5

def _kw_label(entry) -> str:
    return _kw_str(entry)[:16]


# ── Weighted keyword list widget (for main filter fields) ─────────────────────

def kw_widget(fkey: str, label: str, ph: str = "", help_txt: str = ""):
    items: list = st.session_state.cf.setdefault(fkey, [])
    st.markdown(f"**{label}**")
    if help_txt:
        st.caption(help_txt)

    if items:
        chips_html = ""
        for entry in items:
            kw = _kw_str(entry)
            w  = _kw_weight(entry)
            chips_html += (
                f'<span class="kw-chip">🔑 {kw} '
                f'<span style="background:#21262d;border:1px solid #30363d;'
                f'border-radius:3px;padding:0 4px;font-size:10px;color:#8b949e;'
                f'margin-left:3px">w{w}</span></span>'
            )
        st.markdown(chips_html, unsafe_allow_html=True)
        rm_cols = st.columns(min(len(items), 5))
        for i, entry in enumerate(items):
            with rm_cols[i % 5]:
                if st.button(f"✕ {_kw_label(entry)}", key=f"rm_{fkey}_{i}",
                             use_container_width=True):
                    st.session_state.cf[fkey].pop(i)
                    st.rerun()
    else:
        st.caption("_No keywords yet_")

    col_in, col_w, col_btn = st.columns([4, 1, 1])
    with col_in:
        new_val = st.text_input("_", placeholder=ph,
                                label_visibility="collapsed", key=f"inp_{fkey}")
    with col_w:
        new_weight = st.number_input(
            "W", min_value=1, max_value=10, value=5,
            label_visibility="visible", key=f"wgt_{fkey}",
            help="Keyword weight 1 (weak) – 10 (strong)"
        )
    with col_btn:
        st.markdown("<div style='margin-top:28px'>", unsafe_allow_html=True)
        if st.button("＋", key=f"addbtn_{fkey}", use_container_width=True):
            t = new_val.strip()
            existing = [_kw_str(e) for e in st.session_state.cf[fkey]]
            if t and t not in existing:
                st.session_state.cf[fkey].append({"keyword": t, "weight": int(new_weight)})
                st.rerun()
            elif t:
                st.toast("Already in list", icon="⚠️")
        st.markdown("</div>", unsafe_allow_html=True)


# ── Simple keyword list widget (for combination fields — no weights) ──────────

def _simple_kw_widget(items: list, key_prefix: str, label: str, ph: str = ""):
    """In-place keyword list editor that modifies `items` directly."""
    st.markdown(f"**{label}**")
    if items:
        chips_html = "".join(
            f'<span class="kw-chip">🔑 {kw}</span>' for kw in items
        )
        st.markdown(chips_html, unsafe_allow_html=True)
        rm_cols = st.columns(min(len(items), 5))
        for i, kw in enumerate(items):
            with rm_cols[i % 5]:
                if st.button(f"✕ {kw[:16]}", key=f"{key_prefix}_rm_{i}",
                             use_container_width=True):
                    items.pop(i)
                    st.rerun()
    else:
        st.caption("_No keywords_")

    col_in, col_btn = st.columns([5, 1])
    with col_in:
        new_val = st.text_input("_", placeholder=ph,
                                label_visibility="collapsed",
                                key=f"{key_prefix}_inp")
    with col_btn:
        if st.button("＋", key=f"{key_prefix}_add", use_container_width=True):
            t = new_val.strip()
            if t and t not in items:
                items.append(t)
                st.rerun()
            elif t:
                st.toast("Already in list", icon="⚠️")


def _combo_kw_count(combo: dict) -> int:
    return sum(
        len(combo.get(f, []))
        for f in ["url_keywords","req_header_keywords","res_header_keywords",
                  "req_body_keywords","res_body_keywords"]
    )


# ─────────────────────────────────────────────────────────────────────────────
# Page starts here
# ─────────────────────────────────────────────────────────────────────────────

st.markdown("# 🎯 Custom Filter")

if st.button("← Back to Tree"):
    st.switch_page("Home.py")

if not st.session_state.get("tree_data"):
    st.warning("⚠ No HAR analyzed yet — go back and upload a HAR file first.")
    st.stop()

st.markdown("---")

# ── Config name + description ─────────────────────────────────────────────────

col_n, col_d = st.columns([2, 4])
with col_n:
    st.session_state.cf["name"] = st.text_input(
        "Config Name", value=st.session_state.cf.get("name", "My Custom Filter"))
with col_d:
    st.session_state.cf["description"] = st.text_input(
        "Description (optional)", value=st.session_state.cf.get("description", ""),
        placeholder="What does this filter look for?")

# ── Load config from JSON ─────────────────────────────────────────────────────

with st.expander("📂 Load saved config (.json)", expanded=False):

    if st.session_state._cfg_load_msg:
        kind, msg = st.session_state._cfg_load_msg
        if kind == "ok":
            st.markdown(f'<div class="cfg-ok">✅ {msg}</div>', unsafe_allow_html=True)
        else:
            st.markdown(f'<div class="schema-error">❌ {msg}</div>', unsafe_allow_html=True)

    up = st.file_uploader("Upload filter config JSON", type=["json"],
                          key="cfg_upload", label_visibility="collapsed")

    if up is not None:
        file_id = f"{up.name}__{up.size}"
        if st.session_state._last_cfg_file_id != file_id:
            st.session_state._last_cfg_file_id = file_id
            try:
                raw = json.loads(up.read())
                res = _client().validate_filter_config(raw)
                if res.get("valid"):
                    parsed = res["config"]
                    for k in st.session_state.cf:
                        if k in parsed:
                            st.session_state.cf[k] = parsed[k]
                    st.session_state["_mode_radio"] = parsed.get("match_mode", "any_field")
                    n_combos = len(parsed.get("combinations", []))
                    st.session_state._cfg_load_msg = (
                        "ok",
                        f"Config '{parsed.get('name','?')}' loaded. "
                        f"Mode: {parsed.get('match_mode','any_field')}  |  "
                        f"Keywords: url={len(parsed.get('url_keywords',[]))}, "
                        f"req_header={len(parsed.get('req_header_keywords',[]))}, "
                        f"res_body={len(parsed.get('res_body_keywords',[]))}  |  "
                        f"Combinations: {n_combos}"
                    )
                else:
                    st.session_state._cfg_load_msg = (
                        "err", f"Invalid config: {res.get('error','unknown error')}")
            except json.JSONDecodeError:
                st.session_state._cfg_load_msg = ("err", "File is not valid JSON.")
            except Exception as e:
                st.session_state._cfg_load_msg = ("err", str(e))
            st.rerun()

st.markdown("---")

# ── Mode radio ────────────────────────────────────────────────────────────────

mode = st.radio(
    "Filter Mode",
    options=["any_field", "keyword_list"],
    format_func=lambda x: (
        "🏷  Field Keywords  —  match by URL / headers / body  (any field triggers match)"
        if x == "any_field" else
        "🔗  AND Keyword List  —  ALL keywords must appear somewhere in the branch path"
    ),
    key="_mode_radio",
)
st.session_state.cf["match_mode"] = mode

st.markdown("---")

# ── Mode-specific keyword inputs ──────────────────────────────────────────────

if mode == "any_field":
    st.info(
        "A **node matches** if **any** keyword appears in the specified field.  "
        "Matching nodes keep their **entire subtree**.  "
        "Ancestor nodes are kept as path context."
    )

    st.markdown("### 🌐 URL")
    kw_widget("url_keywords", "URL Keywords",
              "e.g. /token  ·  oauth  ·  cognito",
              "Matched against the full request URL")

    st.markdown("---")
    st.markdown("### 📤 Request")
    c1, c2 = st.columns(2)
    with c1:
        kw_widget("req_header_keywords", "Request Header Keywords",
                  "e.g. Authorization  ·  X-Api-Key",
                  "Matched against header name + value")
    with c2:
        kw_widget("req_body_keywords", "Request Body Keywords",
                  "e.g. grant_type  ·  client_id",
                  "Matched against raw + parsed request body")

    st.markdown("---")
    st.markdown("### 📥 Response")
    c3, c4 = st.columns(2)
    with c3:
        kw_widget("res_header_keywords", "Response Header Keywords",
                  "e.g. Set-Cookie  ·  WWW-Authenticate",
                  "Matched against response header name + value")
    with c4:
        kw_widget("res_body_keywords", "Response Body Keywords",
                  "e.g. access_token  ·  id_token",
                  "Matched against raw + parsed response body")

else:  # keyword_list (AND) mode
    st.info(
        "A branch is kept only when **all** keywords are found **somewhere** "
        "in the combined text from the tree root down to that node."
    )
    kw_widget("keyword_list", "Keywords  (ALL must appear in the branch path)",
              "e.g. Authorization  ·  access_token  ·  oauth",
              "Case-insensitive substring match across URL, headers, body")
    kl = st.session_state.cf.get("keyword_list", [])
    if kl:
        st.markdown("**AND expression:** " + " **∧** ".join(
            f"`{_kw_str(k)}`" for k in kl))
    else:
        st.caption("No keywords — filter will return the full tree.")

st.markdown("---")

# ── Combinations ─────────────────────────────────────────────────────────────

st.markdown("### 🔗 Combinations")
st.caption(
    "Each combination is checked across **every branch** (root → node) of the full tree, "
    "field by field.  **All keywords in a combination must appear** in their respective "
    "fields somewhere along the path for a **100 % Found** result.  "
    "Partial matches show the percentage of keywords found."
)

combos: list = st.session_state.cf.setdefault("combinations", [])

# ── Existing combinations ──────────────────────────────────────────────────
for i, combo in enumerate(combos):
    n_kw = _combo_kw_count(combo)
    with st.expander(
        f"🔗 {combo.get('name','Unnamed')} — {n_kw} keyword(s)",
        expanded=False,
    ):
        c_n, c_d, c_del = st.columns([3, 4, 1])
        with c_n:
            combo["name"] = st.text_input(
                "Name", value=combo.get("name", ""),
                key=f"combo_name_{i}", label_visibility="visible")
        with c_d:
            combo["description"] = st.text_input(
                "Description", value=combo.get("description", ""),
                placeholder="What flow does this represent?",
                key=f"combo_desc_{i}", label_visibility="visible")
        with c_del:
            st.markdown("<div style='margin-top:28px'>", unsafe_allow_html=True)
            if st.button("🗑", key=f"del_combo_{i}", use_container_width=True,
                         help="Delete this combination"):
                combos.pop(i)
                st.rerun()
            st.markdown("</div>", unsafe_allow_html=True)

        st.markdown("**Keywords must appear in their specified field along the branch path:**")

        cc1, cc2 = st.columns(2)
        with cc1:
            _simple_kw_widget(
                combo.setdefault("url_keywords", []),
                f"combo_{i}_url", "🌐 URL Keywords", "e.g. /saml/acs")
        with cc2:
            _simple_kw_widget(
                combo.setdefault("req_header_keywords", []),
                f"combo_{i}_rqh", "📤 Request Header Keywords", "e.g. SAMLRequest")

        cc3, cc4 = st.columns(2)
        with cc3:
            _simple_kw_widget(
                combo.setdefault("res_header_keywords", []),
                f"combo_{i}_rsh", "📥 Response Header Keywords", "e.g. Location")
        with cc4:
            _simple_kw_widget(
                combo.setdefault("req_body_keywords", []),
                f"combo_{i}_rqb", "📦 Request Body Keywords", "e.g. SAMLResponse")

        _simple_kw_widget(
            combo.setdefault("res_body_keywords", []),
            f"combo_{i}_rsb", "📨 Response Body Keywords", "e.g. saml:Assertion")

# ── Add new combination ────────────────────────────────────────────────────
if st.button("➕ Add New Combination", use_container_width=False):
    combos.append({
        "name":               f"Combination {len(combos) + 1}",
        "description":        "",
        "url_keywords":       [],
        "req_header_keywords":[],
        "res_header_keywords":[],
        "req_body_keywords":  [],
        "res_body_keywords":  [],
    })
    st.rerun()

st.markdown("---")

# ── Summary + action row ──────────────────────────────────────────────────────

cfg = dict(st.session_state.cf)

if mode == "any_field":
    total_kw = sum(
        len(cfg.get(f, []))
        for f in ["url_keywords","req_header_keywords","res_header_keywords",
                  "req_body_keywords","res_body_keywords"]
    )
    n_combos = len(cfg.get("combinations", []))
    st.caption(
        f"Mode: Field Keywords  ·  **{total_kw}** keyword(s)  ·  **{n_combos}** combination(s)"
    )
    apply_disabled = total_kw == 0 and n_combos == 0
else:
    kl_n = len(cfg.get("keyword_list", []))
    n_combos = len(cfg.get("combinations", []))
    st.caption(f"Mode: AND List  ·  **{kl_n}** keyword(s)  ·  **{n_combos}** combination(s)")
    apply_disabled = kl_n == 0 and n_combos == 0

a1, a2, a3 = st.columns([2, 2, 3])

with a1:
    safe_name = cfg.get("name", "filter").replace(" ", "_").lower()
    st.download_button(
        "⬇ Save Config as JSON",
        data=json.dumps(cfg, indent=2),
        file_name=f"{safe_name}.json",
        mime="application/json",
        use_container_width=True,
    )

with a2:
    if st.button("🗑  Clear All", use_container_width=True):
        for f in ["url_keywords","req_header_keywords","res_header_keywords",
                  "req_body_keywords","res_body_keywords","keyword_list"]:
            st.session_state.cf[f] = []
        st.session_state.cf["combinations"] = []
        st.session_state._cfg_load_msg = None
        st.rerun()

with a3:
    if apply_disabled:
        st.button("✅ Apply Custom Filter", type="primary",
                  use_container_width=True, disabled=True)
        st.caption("⚠ Add at least one keyword or combination to enable Apply.")
    else:
        if st.button("✅ Apply Custom Filter", type="primary",
                     use_container_width=True):
            with st.spinner("Applying filter…"):
                try:
                    res = _client().filter_custom(st.session_state.tree_data, cfg)
                    st.session_state.display_data         = res
                    st.session_state.filter_mode          = "custom"
                    st.session_state.custom_filter_config = cfg
                    st.session_state.match_info           = res.get("match_info", [])
                    st.session_state.keyword_summary      = res.get("keyword_summary", {})
                    st.session_state.protocol_score       = res.get("protocol_score", None)
                    st.session_state.combination_results  = res.get("combination_results", [])
                    st.session_state.last_error           = None
                    st.success(f"✅ {res.get('total_custom_nodes', 0)} matching node(s).")
                    st.switch_page("Home.py")
                except Exception as e:
                    st.error(str(e))

st.markdown("---")

with st.expander("🔎 Preview config JSON"):
    st.json(cfg)