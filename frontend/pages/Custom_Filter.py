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
/* ── Keyword chips ── */
.kw-chip{display:inline-flex;align-items:center;gap:6px;background:#1c2128;
  border:1px solid #30363d;border-radius:16px;padding:3px 10px;font-size:12px;
  font-family:monospace;color:#e6edf3;margin:3px 3px 3px 0}

/* ── Status banners ── */
.schema-error{background:rgba(248,81,73,.1);border:1px solid rgba(248,81,73,.4);
  border-radius:8px;padding:10px 14px;color:#f85149;font-size:13px}
.cfg-ok{background:rgba(63,185,80,.1);border:1px solid rgba(63,185,80,.4);
  border-radius:8px;padding:10px 14px;color:#3fb950;font-size:13px}

/* ── Panel cards ── */
.panel-card{background:#0d1117;border:1px solid #21262d;border-radius:10px;
  padding:18px 20px;height:100%}
.panel-header{font-size:15px;font-weight:600;color:#e6edf3;margin-bottom:4px;
  display:flex;align-items:center;gap:8px}
.panel-sub{font-size:12px;color:#8b949e;margin-bottom:14px;line-height:1.5}

/* ── How-it-works callout ── */
.flow-banner{background:#0d1117;border:1px solid #388bfd44;border-radius:10px;
  padding:14px 18px;margin:0 0 18px 0}
.flow-banner .flow-title{font-size:13px;font-weight:600;color:#79c0ff;
  margin-bottom:8px;letter-spacing:.03em}
.flow-step{display:flex;align-items:flex-start;gap:10px;margin:6px 0}
.flow-num{background:#1f6feb;color:#fff;border-radius:50%;width:20px;height:20px;
  font-size:11px;font-weight:700;display:flex;align-items:center;justify-content:center;
  flex-shrink:0;margin-top:1px}
.flow-text{font-size:12px;color:#c9d1d9;line-height:1.5}
.flow-text b{color:#e6edf3}
.flow-arrow{color:#30363d;font-size:18px;margin:0 4px}

/* ── Tip box ── */
.tip-box{background:#161b22;border:1px solid #f0883e44;border-radius:8px;
  padding:10px 14px;margin:10px 0 6px 0}
.tip-box .tip-title{font-size:11px;font-weight:600;color:#f0883e;
  text-transform:uppercase;letter-spacing:.06em;margin-bottom:4px}
.tip-box p{font-size:12px;color:#c9d1d9;margin:0;line-height:1.5}

/* ── Section divider inside columns ── */
.sec-divider{border:none;border-top:1px solid #21262d;margin:14px 0}

/* ── Combo card ── */
.combo-card{background:#161b22;border:1px solid #30363d;border-radius:8px;
  padding:12px 16px;margin:6px 0}

/* ── Mode pill ── */
.mode-pill{display:inline-block;background:#1f6feb22;border:1px solid #1f6feb88;
  border-radius:20px;padding:2px 10px;font-size:11px;color:#79c0ff;font-weight:600;
  letter-spacing:.04em}
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


# ── Weighted keyword list widget ──────────────────────────────────────────────

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

    new_val = st.text_input("_", placeholder=ph,
                            label_visibility="collapsed", key=f"inp_{fkey}")
    new_weight = st.number_input(
        "Weight (1–10)", min_value=1, max_value=10, value=5,
        key=f"wgt_{fkey}", help="Keyword weight 1 (weak) – 10 (strong)"
    )
    if st.button(f"＋ Add to {label}", key=f"addbtn_{fkey}", use_container_width=True):
        t = new_val.strip()
        existing = [_kw_str(e) for e in st.session_state.cf[fkey]]
        if t and t not in existing:
            st.session_state.cf[fkey].append({"keyword": t, "weight": int(new_weight)})
            st.rerun()
        elif t:
            st.toast("Already in list", icon="⚠️")


# ── Simple keyword list widget (combination fields — no weights) ──────────────

def _simple_kw_widget(items: list, key_prefix: str, label: str, ph: str = ""):
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

    new_val = st.text_input("_", placeholder=ph,
                            label_visibility="collapsed",
                            key=f"{key_prefix}_inp")
    if st.button(f"＋ Add to {label}", key=f"{key_prefix}_add", use_container_width=True):
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


# ═════════════════════════════════════════════════════════════════════════════
# PAGE
# ═════════════════════════════════════════════════════════════════════════════

st.markdown("# 🎯 Custom Filter & Combination Search")

if st.button("← Back to Tree"):
    st.switch_page("Home.py")

if not st.session_state.get("tree_data"):
    st.warning("⚠ No HAR analyzed yet — go back and upload a HAR file first.")
    st.stop()

# ── How it works — flow banner ────────────────────────────────────────────────

st.markdown("""
<div class="flow-banner">
  <div class="flow-title">⚡ How the two tools work together</div>
  <div style="display:flex;align-items:center;flex-wrap:wrap;gap:4px">
    <div class="flow-step">
      <div class="flow-num">1</div>
      <div class="flow-text">
        <b>Keyword Filter</b> (left panel) — prunes the tree. Nodes whose
        URL / headers / body contain a keyword are kept, <b>along with their
        entire child subtree</b>. Ancestors are kept as path context.
        Nodes with no match anywhere in their branch are dropped.
      </div>
    </div>
    <span class="flow-arrow">→</span>
    <div class="flow-step">
      <div class="flow-num">2</div>
      <div class="flow-text">
        <b>Combination Search</b> (right panel) — scores the filtered tree.
        Each combination checks whether <b>all its keywords appear somewhere
        across the surviving nodes</b> (any field, any node) and returns a
        <b>% match + verdict</b>. It never drops nodes — it only measures.
      </div>
    </div>
    <span class="flow-arrow">→</span>
    <div class="flow-step">
      <div class="flow-num">3</div>
      <div class="flow-text">
        <b>Protocol Score</b> blends both signals into a final
        Confirmed / Likely / Possible / Not detected verdict shown on the
        tree view after you hit Apply.
      </div>
    </div>
  </div>
</div>
""", unsafe_allow_html=True)

st.markdown("---")

# ── Config name / description / load ─────────────────────────────────────────

col_n, col_d = st.columns([2, 4])
with col_n:
    st.session_state.cf["name"] = st.text_input(
        "Config Name", value=st.session_state.cf.get("name", "My Custom Filter"))
with col_d:
    st.session_state.cf["description"] = st.text_input(
        "Description (optional)", value=st.session_state.cf.get("description", ""),
        placeholder="What does this filter look for?")

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

# ═════════════════════════════════════════════════════════════════════════════
# MAIN TWO-COLUMN LAYOUT
# ═════════════════════════════════════════════════════════════════════════════

tab_filter, tab_combo = st.tabs(["🏷️  Keyword Filter", "🔗  Combination Search"])

# ─────────────────────────────────────────────────────────────────────────────
# TAB 1 — KEYWORD FILTER
# ─────────────────────────────────────────────────────────────────────────────

with tab_filter:
    st.markdown("""
    <div class="panel-header">🏷️ Keyword Filter</div>
    <div class="panel-sub">
      Prunes the HAR tree to nodes that match your keywords.
      <b>When a node matches, its entire child subtree is kept</b> — you see the
      full downstream context, not just the matching line.<br>
      Nodes that don't match anywhere in their branch are removed from the tree view.
    </div>
    """, unsafe_allow_html=True)

    # Mode radio
    mode = st.radio(
        "Match mode",
        options=["any_field", "keyword_list"],
        format_func=lambda x: (
            "🏷 Field Keywords — any matching field triggers the node"
            if x == "any_field" else
            "🔗 AND List — ALL keywords must appear somewhere in the branch path"
        ),
        key="_mode_radio",
    )
    st.session_state.cf["match_mode"] = mode

    st.markdown("<hr class='sec-divider'>", unsafe_allow_html=True)

    if mode == "any_field":
        st.markdown("""
        <div class="tip-box">
          <div class="tip-title">📌 What happens when you apply</div>
          <p>Each node is checked individually. If <em>any</em> keyword is found in
          its designated field (URL, request header, response body, etc.), that node
          is kept and <b>all its children are preserved automatically</b> — no need
          to add child-level keywords. Ancestor nodes are included as context even
          if they don't match. Non-matching leaf branches are pruned.</p>
        </div>
        """, unsafe_allow_html=True)

        st.markdown("#### 🌐 URL")
        kw_widget("url_keywords", "URL Keywords",
                  "e.g. /token  ·  oauth  ·  SAMLRequest",
                  "Matched against the full request URL and decoded query param keys + values")

        st.markdown("<hr class='sec-divider'>", unsafe_allow_html=True)
        st.markdown("#### 📤 Request")
        kw_widget("req_header_keywords", "Header Keywords",
                  "e.g. Authorization  ·  X-Api-Key",
                  "Matched against header names and decoded values")
        kw_widget("req_body_keywords", "Body Keywords",
                  "e.g. grant_type  ·  client_id",
                  "Matched against raw + decoded request body")

        st.markdown("<hr class='sec-divider'>", unsafe_allow_html=True)
        st.markdown("#### 📥 Response")
        kw_widget("res_header_keywords", "Header Keywords",
                  "e.g. Set-Cookie  ·  WWW-Authenticate",
                  "Matched against response header names and decoded values")
        kw_widget("res_body_keywords", "Body Keywords",
                  "e.g. access_token  ·  id_token",
                  "Matched against raw + decoded response body")

    else:  # keyword_list (AND) mode
        st.markdown("""
        <div class="tip-box">
          <div class="tip-title">📌 What happens when you apply</div>
          <p>A branch (root → node path) is kept only when the <b>combined text
          of every node along that path</b> collectively contains <em>all</em> your
          keywords. One keyword can be in the URL, another in a response body further
          down — they just all need to appear somewhere on the path. Branches missing
          even one keyword are dropped entirely.</p>
        </div>
        """, unsafe_allow_html=True)

        kw_widget("keyword_list", "Keywords (ALL must appear in the branch path)",
                  "e.g. Authorization  ·  access_token  ·  oauth",
                  "Case-insensitive substring match across URL, headers, body")
        kl = st.session_state.cf.get("keyword_list", [])
        if kl:
            st.markdown("**AND expression:** " + " **∧** ".join(
                f"`{_kw_str(k)}`" for k in kl))
        else:
            st.caption("No keywords — filter will return the full tree.")

    # Keyword filter summary
    st.markdown("<hr class='sec-divider'>", unsafe_allow_html=True)
    if mode == "any_field":
        total_kw = sum(
            len(st.session_state.cf.get(f, []))
            for f in ["url_keywords","req_header_keywords","res_header_keywords",
                      "req_body_keywords","res_body_keywords"]
        )
        if total_kw:
            st.success(f"**{total_kw}** keyword(s) configured across field filters.")
        else:
            st.caption("No keywords yet — tree will be returned unfiltered.")
    else:
        kl_n = len(st.session_state.cf.get("keyword_list", []))
        if kl_n:
            st.success(f"**{kl_n}** AND keyword(s) configured.")
        else:
            st.caption("No keywords yet — tree will be returned unfiltered.")


# ─────────────────────────────────────────────────────────────────────────────
# TAB 2 — COMBINATION SEARCH
# ─────────────────────────────────────────────────────────────────────────────

with tab_combo:
    st.markdown("""
    <div class="panel-header">🔗 Combination Search</div>
    <div class="panel-sub">
      Measures how strongly a protocol or flow is present in the tree.
      A combination groups keywords by field — each keyword can appear in
      <em>any</em> node, not necessarily the same one.
      <b>Combinations never remove nodes</b> — they only produce a match % and
      a verdict (Confirmed / Likely / Possible / Not detected).
    </div>
    """, unsafe_allow_html=True)

    st.markdown("""
    <div class="tip-box">
      <div class="tip-title">💡 How to use combinations</div>
      <p>
        <b>Multi-signal detection:</b> Group keywords that together prove a flow —
        e.g. <code>SAMLRequest</code> in URL + <code>SAMLResponse</code> in request
        body + <code>StatusCode</code> in response body. All three must appear
        (in any nodes) for 100 % Found.<br><br>
        <b>Single keyword search:</b> Add a combination with just <em>one</em>
        keyword in the relevant field. You get a precise Found / Not found result
        plus every node where it appears — without filtering the tree at all.
        Leave the keyword filter empty and use only a combination when you want
        presence detection without pruning.
      </p>
    </div>
    """, unsafe_allow_html=True)

    st.markdown("<hr class='sec-divider'>", unsafe_allow_html=True)

    combos: list = st.session_state.cf.setdefault("combinations", [])

    if not combos:
        st.markdown("""
        <div style="text-align:center;padding:24px 0;color:#484f58">
          <div style="font-size:28px;margin-bottom:8px">🔗</div>
          <div style="font-size:13px">No combinations yet.<br>
          Add one below to start scoring protocol presence.</div>
        </div>
        """, unsafe_allow_html=True)

    for i, combo in enumerate(combos):
        n_kw = _combo_kw_count(combo)
        with st.expander(
            f"🔗 {combo.get('name','Unnamed')} — {n_kw} keyword(s)",
            expanded=(n_kw == 0),
        ):
            c_n, c_d, c_del = st.columns([3, 4, 1])
            with c_n:
                combo["name"] = st.text_input(
                    "Name", value=combo.get("name", ""),
                    key=f"combo_name_{i}", label_visibility="visible")
            with c_d:
                combo["description"] = st.text_input(
                    "Description", value=combo.get("description", ""),
                    placeholder="e.g. SAML SP-initiated SSO flow",
                    key=f"combo_desc_{i}", label_visibility="visible")
            with c_del:
                st.markdown("<div style='margin-top:28px'>", unsafe_allow_html=True)
                if st.button("🗑", key=f"del_combo_{i}", use_container_width=True,
                             help="Delete this combination"):
                    combos.pop(i)
                    st.rerun()
                st.markdown("</div>", unsafe_allow_html=True)

            st.caption(
                "Each keyword below is searched in its designated field across **all nodes** "
                "in the (filtered) tree. A keyword found in the wrong field is still matched "
                "via fallback — the result shows where it was actually found."
            )

            cc1, cc2 = st.columns(2)
            with cc1:
                _simple_kw_widget(
                    combo.setdefault("url_keywords", []),
                    f"combo_{i}_url", "🌐 URL", "e.g. /saml/acs  ·  SAMLRequest")
            with cc2:
                _simple_kw_widget(
                    combo.setdefault("req_header_keywords", []),
                    f"combo_{i}_rqh", "📤 Request Header", "e.g. Authorization")

            cc3, cc4 = st.columns(2)
            with cc3:
                _simple_kw_widget(
                    combo.setdefault("res_header_keywords", []),
                    f"combo_{i}_rsh", "📥 Response Header", "e.g. Location  ·  Set-Cookie")
            with cc4:
                _simple_kw_widget(
                    combo.setdefault("req_body_keywords", []),
                    f"combo_{i}_rqb", "📦 Request Body", "e.g. SAMLResponse  ·  grant_type")

            _simple_kw_widget(
                combo.setdefault("res_body_keywords", []),
                f"combo_{i}_rsb", "📨 Response Body", "e.g. access_token  ·  StatusCode")

    if st.button("➕ Add Combination", use_container_width=False):
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

    # Combinations summary
    st.markdown("<hr class='sec-divider'>", unsafe_allow_html=True)
    n_combos = len(combos)
    total_combo_kw = sum(_combo_kw_count(c) for c in combos)
    if n_combos:
        st.success(f"**{n_combos}** combination(s) · **{total_combo_kw}** total keyword(s)")
    else:
        st.caption("No combinations — protocol scoring will be skipped.")


# ═════════════════════════════════════════════════════════════════════════════
# ACTION BAR
# ═════════════════════════════════════════════════════════════════════════════

st.markdown("---")

cfg = dict(st.session_state.cf)
mode = st.session_state.cf.get("match_mode", "any_field")

if mode == "any_field":
    total_kw = sum(
        len(cfg.get(f, []))
        for f in ["url_keywords","req_header_keywords","res_header_keywords",
                  "req_body_keywords","res_body_keywords"]
    )
else:
    total_kw = len(cfg.get("keyword_list", []))

n_combos = len(cfg.get("combinations", []))
apply_disabled = total_kw == 0 and n_combos == 0

a1, a2, a3, a4 = st.columns([2, 2, 1, 3])

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
    pass  # spacer

with a4:
    mode_label = "Field Keywords" if mode == "any_field" else "AND List"
    kw_part = f"**{total_kw}** kw" if total_kw else "no keywords"
    combo_part = f"**{n_combos}** combo(s)" if n_combos else "no combos"
    st.caption(f"Mode: {mode_label}  ·  {kw_part}  ·  {combo_part}")

    if apply_disabled:
        st.button("✅ Apply Filter & Score", type="primary",
                  use_container_width=True, disabled=True)
        st.caption("⚠ Add at least one keyword or combination to enable.")
    else:
        if st.button("✅ Apply Filter & Score", type="primary",
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