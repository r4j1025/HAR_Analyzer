"""
utils/tree_renderer.py
──────────────────────
Generates a self-contained HTML document that renders an interactive
request/response tree inside a Streamlit st.components.v1.html iframe.

Layout:
  toolbar
  ┌─────────────────────┬──────────────────────────┐
  │  tree panel (left)  │  detail panel (right)    │
  └─────────────────────┴──────────────────────────┘
  match panel  (shown only when filter is active)

New in v3:
  - Tree always shows all nodes initially.
  - match_info accepted; rendered as a clickable keyword-hit panel below the tree.
  - Clicking a match button jumps to the node and highlights matched text in detail.
  - Matched keywords highlighted with <mark> inside the detail panel.
"""
from __future__ import annotations

import copy
import json

MAX_BODY_CHARS = 200_000


# ── Public entry point ────────────────────────────────────────────────────────

def render_tree_html(
    tree_data: dict,
    filter_mode: str = "none",
    match_info: list = None,
    height: int = 800,
) -> str:
    safe_data = _truncate_bodies(copy.deepcopy(tree_data))
    raw_json = json.dumps(safe_data, ensure_ascii=False)
    safe_json = (
        raw_json
        .replace("</script>", r"<\/script>")
        .replace("<!--",       r"<\!--")
    )

    mi = match_info or []
    mi_json = json.dumps(mi, ensure_ascii=False)
    safe_mi = (
        mi_json
        .replace("</script>", r"<\/script>")
        .replace("<!--",       r"<\!--")
    )

    filter_mode_json = json.dumps(filter_mode)
    height_inner = height - 4  # tiny buffer

    html = _TEMPLATE.replace("__TREE_DATA__", safe_json)
    html = html.replace("__FILTER_MODE__", filter_mode_json)
    html = html.replace("__MATCH_INFO__", safe_mi)
    html = html.replace("__HEIGHT__", str(height_inner))
    return html


# ── Body truncation ───────────────────────────────────────────────────────────

def _truncate_str(s, limit: int = MAX_BODY_CHARS) -> str:
    if s and len(s) > limit:
        return s[:limit] + f"\n… [truncated {len(s)-limit:,} chars]"
    return s


def _truncate_node(node: dict) -> dict:
    for side in ("request", "response"):
        part = node.get(side)
        if not part:
            continue
        if part.get("body"):
            part["body"] = _truncate_str(part["body"])
        bp = part.get("body_parsed")
        if bp is not None:
            bp_str = json.dumps(bp, ensure_ascii=False)
            if len(bp_str) > MAX_BODY_CHARS:
                part["body_parsed"] = None
    return node


def _truncate_bodies(data: dict) -> dict:
    def walk(node: dict):
        _truncate_node(node)
        for child in node.get("children", []):
            walk(child)
    if data.get("tree"):
        walk(data["tree"])
    for orphan in data.get("orphan_nodes", []):
        walk(orphan)
    return data


# ── HTML template ─────────────────────────────────────────────────────────────

_TEMPLATE = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<style>
:root {
  --bg:#0d1117; --surface:#161b22; --surface2:#1c2128; --border:#30363d;
  --accent:#58a6ff; --accent2:#3fb950; --warn:#d29922; --danger:#f85149;
  --success:#3fb950; --text:#e6edf3; --muted:#8b949e;
  --auth:#f0883e; --custom:#bc8cff;
  --hl-bg:#3d2b00; --hl-text:#ffd666; --hl-border:#b8860b;
  --mono:'JetBrains Mono','Fira Code',monospace;
}
*{box-sizing:border-box;margin:0;padding:0}
html,body{height:100%;background:var(--bg);color:var(--text);font-family:'Segoe UI',system-ui,sans-serif;font-size:13px;overflow:hidden}

/* ── Layout ── */
.app{display:flex;flex-direction:column;height:__HEIGHT__px}
.main{display:grid;grid-template-columns:310px 1fr;flex:1;overflow:hidden;min-height:0}

/* ── Toolbar ── */
.toolbar{
  background:var(--surface);border-bottom:1px solid var(--border);flex-shrink:0;
  display:flex;align-items:center;gap:8px;padding:0 12px;height:44px;
}
.search-wrap{flex:1;position:relative;max-width:380px}
.search-wrap input{
  width:100%;background:var(--surface2);border:1px solid var(--border);
  border-radius:6px;padding:5px 10px 5px 28px;color:var(--text);
  font-size:12px;outline:none;font-family:var(--mono);
}
.search-wrap input:focus{border-color:var(--accent)}
.search-icon{position:absolute;left:9px;top:50%;transform:translateY(-50%);color:var(--muted);font-size:11px;pointer-events:none}
.tbtn{
  background:var(--surface2);border:1px solid var(--border);border-radius:5px;
  color:var(--text);cursor:pointer;font-size:11px;padding:4px 10px;
  white-space:nowrap;transition:background .12s;
}
.tbtn:hover{background:var(--border)}
.stat-chip{
  font-family:var(--mono);font-size:10px;color:var(--muted);
  padding:2px 8px;border-radius:10px;border:1px solid var(--border);
  background:var(--surface2);
}
.stat-chip.auth{color:var(--auth);border-color:rgba(240,136,62,.3);background:rgba(240,136,62,.08)}
.stat-chip.custom{color:var(--custom);border-color:rgba(188,140,255,.3);background:rgba(188,140,255,.08)}
.ml{margin-left:auto}

/* ── Tree panel ── */
.tree-panel{border-right:1px solid var(--border);overflow-y:auto;overflow-x:hidden}
.tree-panel::-webkit-scrollbar{width:4px}
.tree-panel::-webkit-scrollbar-thumb{background:var(--border);border-radius:2px}
.section-lbl{
  padding:5px 12px;font-size:10px;font-weight:700;letter-spacing:.1em;
  text-transform:uppercase;color:var(--muted);background:var(--surface);
  border-bottom:1px solid var(--border);position:sticky;top:0;z-index:5;
}

/* ── Tree nodes ── */
.trow{
  display:flex;align-items:center;gap:5px;padding:4px 12px;
  cursor:pointer;border-left:3px solid transparent;min-height:26px;
  transition:background .1s;
}
.trow:hover{background:var(--surface2)}
.trow.selected{background:rgba(88,166,255,.1);border-left-color:var(--accent)}
.trow.filter-match{border-left-color:var(--auth)!important}
.trow.hidden{display:none}

.toggle{flex-shrink:0;width:14px;text-align:center;color:var(--muted);font-size:10px;user-select:none}
.mbadge{
  flex-shrink:0;font-family:var(--mono);font-size:9px;font-weight:700;
  padding:1px 5px;border-radius:3px;letter-spacing:.05em;
}
.mGET   {background:rgba(63,185,80,.12);color:#3fb950;border:1px solid rgba(63,185,80,.25)}
.mPOST  {background:rgba(88,166,255,.12);color:#58a6ff;border:1px solid rgba(88,166,255,.25)}
.mPUT   {background:rgba(210,153,34,.12);color:#d29922;border:1px solid rgba(210,153,34,.25)}
.mDELETE{background:rgba(248,81,73,.12);color:#f85149;border:1px solid rgba(248,81,73,.25)}
.mPATCH {background:rgba(188,140,255,.12);color:#bc8cff;border:1px solid rgba(188,140,255,.25)}
.mOTHER {background:rgba(139,148,158,.12);color:#8b949e;border:1px solid rgba(139,148,158,.25)}

.nurl{flex:1;font-family:var(--mono);font-size:11px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.sdot{flex-shrink:0;width:7px;height:7px;border-radius:50%}
.s2{background:var(--success)} .s3{background:var(--warn)}
.s4{background:var(--danger);opacity:.7} .s5{background:var(--danger)} .s0{background:var(--muted)}

/* ── Detail panel ── */
.detail{overflow-y:auto;background:var(--bg)}
.detail::-webkit-scrollbar{width:4px}
.detail::-webkit-scrollbar-thumb{background:var(--border);border-radius:2px}
.empty-state{display:flex;flex-direction:column;align-items:center;justify-content:center;height:100%;color:var(--muted);gap:10px}
.empty-state .big{font-size:36px}

.dheader{
  padding:14px 18px;border-bottom:1px solid var(--border);
  background:var(--surface);position:sticky;top:0;z-index:10;
}
.durl{font-family:var(--mono);font-size:12px;word-break:break-all;color:var(--accent);margin-bottom:8px}
.dmeta{display:flex;align-items:center;gap:10px;flex-wrap:wrap}

.copy-bar{
  display:flex;gap:8px;padding:7px 18px;
  background:var(--surface2);border-bottom:1px solid var(--border);
}
.cbtn{
  background:var(--surface);border:1px solid var(--border);border-radius:4px;
  color:var(--muted);cursor:pointer;font-size:11px;padding:3px 10px;
  transition:background .1s,color .1s;
}
.cbtn:hover{background:var(--border);color:var(--text)}
.cbtn.ok{background:rgba(63,185,80,.15);border-color:var(--success);color:var(--success)}

/* ── Detail sections ── */
.sec{border-bottom:1px solid var(--border)}
.sec-h{
  display:flex;align-items:center;justify-content:space-between;
  padding:9px 18px;cursor:pointer;font-size:11px;font-weight:700;
  letter-spacing:.05em;color:var(--muted);user-select:none;text-transform:uppercase;
}
.sec-h:hover{background:var(--surface2)}
.sec-body{display:none;padding:4px 18px 12px}
.sec-body.open{display:block}
.kv{width:100%;border-collapse:collapse;font-family:var(--mono);font-size:11px}
.kv td{padding:3px 8px 3px 0;vertical-align:top;border-bottom:1px solid var(--border)}
.kv td:first-child{width:36%;color:var(--muted);word-break:break-word}
.kv td:last-child{color:var(--text);word-break:break-all}
.bpre{
  background:var(--surface2);border:1px solid var(--border);border-radius:6px;
  padding:10px;font-family:var(--mono);font-size:11px;white-space:pre-wrap;
  word-break:break-all;max-height:280px;overflow-y:auto;color:var(--text);margin-top:4px;
}
.pill{font-family:var(--mono);font-size:10px;padding:2px 8px;border-radius:10px;border:1px solid}
.ppage{color:var(--accent);border-color:rgba(88,166,255,.3);background:rgba(88,166,255,.1)}
.papi{color:var(--accent2);border-color:rgba(63,185,80,.3);background:rgba(63,185,80,.1)}
.predir{color:var(--warn);border-color:rgba(210,153,34,.3);background:rgba(210,153,34,.1)}
.pws{color:var(--custom);border-color:rgba(188,140,255,.3);background:rgba(188,140,255,.1)}
.no-data{color:var(--muted);font-size:11px;font-family:var(--mono);padding:4px 0}

/* ── Keyword highlight ── */
mark.kw-hl{
  background:var(--hl-bg);color:var(--hl-text);
  border-radius:2px;padding:0 2px;font-weight:700;
  box-shadow:0 0 0 1px var(--hl-border);
}

/* ── Match panel ── */
.match-panel{
  flex-shrink:0;background:var(--surface);border-top:1px solid var(--border);
  max-height:160px;overflow:hidden;display:flex;flex-direction:column;
}
.match-panel.hidden{display:none}
.match-header{
  display:flex;align-items:center;gap:8px;padding:5px 12px;
  background:var(--surface2);border-bottom:1px solid var(--border);
  font-size:11px;font-weight:700;letter-spacing:.05em;
  text-transform:uppercase;color:var(--auth);flex-shrink:0;cursor:pointer;
  user-select:none;
}
.match-header .mc{color:var(--muted);font-weight:400;margin-left:4px}
.match-header .chev{margin-left:auto;color:var(--muted)}
.match-body{overflow-x:auto;overflow-y:auto;padding:7px 12px;flex:1;display:flex;flex-wrap:wrap;gap:5px;align-content:flex-start}
.match-body::-webkit-scrollbar{height:4px;width:4px}
.match-body::-webkit-scrollbar-thumb{background:var(--border);border-radius:2px}
.match-body.collapsed{display:none}

/* match keyword button */
.mkw-btn{
  display:inline-flex;align-items:center;gap:5px;
  background:var(--surface2);border:1px solid var(--border);border-radius:14px;
  color:var(--text);cursor:pointer;font-family:var(--mono);font-size:11px;
  padding:3px 10px;transition:background .12s,border-color .12s;white-space:nowrap;
  max-width:300px;overflow:hidden;text-overflow:ellipsis;
}
.mkw-btn:hover{background:rgba(240,136,62,.15);border-color:var(--auth);color:var(--auth)}
.mkw-btn.active{background:rgba(240,136,62,.2);border-color:var(--auth);color:var(--auth)}
.mkw-kw{color:var(--auth);font-weight:700}
.mkw-field{color:var(--muted);font-size:9px;text-transform:uppercase;letter-spacing:.05em}
.mkw-path{color:var(--muted);font-size:10px;overflow:hidden;text-overflow:ellipsis;max-width:160px;white-space:nowrap}

/* ── Encoding indicator badges ── */
.enc-badge{display:inline-flex;align-items:center;font-family:var(--mono);font-size:9px;
  font-weight:700;padding:0 5px;border-radius:8px;margin:0 2px;vertical-align:middle;
  cursor:default;letter-spacing:.03em;user-select:none}
.enc-url {background:rgba(63,185,80,.12);color:#3fb950;border:1px solid rgba(63,185,80,.3)}
.enc-b64 {background:rgba(88,166,255,.12);color:#58a6ff;border:1px solid rgba(88,166,255,.3)}
.enc-jwt {background:rgba(240,136,62,.15);color:#f0883e;border:1px solid rgba(240,136,62,.35)}
.enc-hex {background:rgba(188,140,255,.12);color:#bc8cff;border:1px solid rgba(188,140,255,.3)}
.enc-html{background:rgba(210,153,34,.12);color:#d29922;border:1px solid rgba(210,153,34,.3)}

/* ── Decode popup ── */
.decode-popup{position:fixed;z-index:9999;background:var(--surface);border:1px solid var(--border);
  border-radius:8px;padding:10px 12px;box-shadow:0 8px 28px rgba(0,0,0,.6);
  min-width:240px;max-width:300px;display:none}
.decode-popup.visible{display:block}
.decode-popup-title{font-size:10px;font-weight:700;color:var(--muted);text-transform:uppercase;
  letter-spacing:.07em;margin-bottom:7px;padding-bottom:6px;border-bottom:1px solid var(--border)}
.decode-opts{display:flex;flex-wrap:wrap;gap:4px;margin-top:5px}
.decode-btn{background:var(--surface2);border:1px solid var(--border);border-radius:4px;
  color:var(--text);cursor:pointer;font-size:11px;padding:3px 9px;font-family:var(--mono);
  transition:background .1s}
.decode-btn:hover{background:var(--border)}
.decode-btn.detected{border-color:var(--accent);color:var(--accent);font-weight:700}
.decode-close{position:absolute;top:7px;right:9px;background:none;border:none;
  color:var(--muted);cursor:pointer;font-size:13px;line-height:1;padding:0 2px}
.decode-close:hover{color:var(--text)}

/* ── Decode result panel ── */
.decode-result-panel{position:fixed;z-index:9998;background:var(--surface);
  border:1px solid var(--border);border-radius:8px;padding:10px 12px;
  box-shadow:0 8px 28px rgba(0,0,0,.6);display:none;flex-direction:column;gap:7px}
.decode-result-panel.visible{display:flex}
.decode-result-header{display:flex;align-items:center;justify-content:space-between;
  font-size:10px;font-weight:700;color:var(--muted);text-transform:uppercase;letter-spacing:.07em}
.decode-result-body{background:var(--surface2);border:1px solid var(--border);border-radius:4px;
  padding:8px;font-family:var(--mono);font-size:11px;white-space:pre-wrap;
  word-break:break-all;overflow-y:auto;max-height:200px;color:var(--text);margin:0}
.decode-result-actions{display:flex;gap:6px}
.decode-ra-btn{background:var(--surface);border:1px solid var(--border);border-radius:4px;
  color:var(--muted);cursor:pointer;font-size:11px;padding:3px 10px;
  transition:background .1s,color .1s}
.decode-ra-btn:hover{background:var(--border);color:var(--text)}
.decode-ra-btn.ok{background:rgba(63,185,80,.15);border-color:var(--success);color:var(--success)}
.enc-hint{font-size:10px;color:var(--muted);margin-bottom:5px;display:flex;align-items:center;gap:5px;flex-wrap:wrap}
#decBreadcrumb{display:flex}
.body-kv-tbl td{border-top:1px solid var(--border);font-family:var(--mono);font-size:12px}
.enc-badge[onclick]{transition:opacity .1s}.enc-badge[onclick]:hover{opacity:.7}
</style>
</head>
<body>
<div class="app">

  <!-- toolbar -->
  <div class="toolbar">
    <div class="search-wrap">
      <span class="search-icon">⌕</span>
      <input id="srch" type="text" placeholder="Search URL · method · status…" oninput="doSearch(this.value)">
    </div>
    <button class="tbtn" onclick="expandAll()">⊞ Expand</button>
    <button class="tbtn" onclick="collapseAll()">⊟ Collapse</button>
    <button class="tbtn" onclick="copyAll()">⎘ JSON</button>
    <span class="ml"></span>
    <span class="stat-chip" id="countChip"></span>
  </div>

  <!-- tree + detail -->
  <div class="main">
    <div class="tree-panel" id="treePanel"></div>
    <div class="detail" id="detailPanel">
      <div class="empty-state">
        <span class="big">↖</span>
        <span>Click a node to inspect it</span>
      </div>
    </div>
  </div>

  <!-- match panel -->
  <div class="match-panel hidden" id="matchPanel">
    <div class="match-header" id="matchHeader" onclick="toggleMatchBody()">
      <span>🔑 Matched Keywords</span>
      <span class="mc" id="matchCount"></span>
      <span class="chev" id="matchChev">▾</span>
    </div>
    <div class="match-body" id="matchBody"></div>
  </div>
</div>

<script>
/* ─────────────────────────────────────────────────────────────────────────── */
const DATA        = __TREE_DATA__;
const FILTER_MODE = __FILTER_MODE__;
const MATCH_INFO  = __MATCH_INFO__;

let activeNode    = null;
let activeNodeId  = null;
let activeMatchBtn = null;

/* Maps node id → {row, data, depth, childWrap, toggle, parentRow} */
const nodeRowMap  = {};
const nodeDataMap = {};

/* Per-node match keywords for highlighting */
const nodeMatchKws = {};   /* node_id → Set<string> */
MATCH_INFO.forEach(mi => {
  const set = new Set();
  (mi.matches || []).forEach(m => set.add(m.keyword.toLowerCase()));
  nodeMatchKws[mi.node_id] = set;
});

/* ── Count ─────────────────────────────────────────────────────────────────── */
function count(n){ if(!n) return 0; return 1+(n.children||[]).reduce((s,c)=>s+count(c),0); }

/* ── Build tree ────────────────────────────────────────────────────────────── */
function init(){
  const panel = document.getElementById('treePanel');
  panel.innerHTML = '';

  try {
    if(DATA.tree){
      const sec = document.createElement('div');
      const lbl = document.createElement('div');
      lbl.className = 'section-lbl';
      const treeCount = count(DATA.tree);
      lbl.textContent = 'Main Tree  ·  '+(DATA.root_url||'')+'  ['+treeCount+' nodes]';
      sec.appendChild(lbl);
      sec.appendChild(buildNode(DATA.tree, 0, true));
      panel.appendChild(sec);
    }

    if(DATA.orphan_nodes?.length){
      const sec = document.createElement('div');
      const lbl = document.createElement('div');
      lbl.className = 'section-lbl';
      lbl.textContent = 'Orphan Nodes (Cross-Domain)  ·  '+DATA.orphan_nodes.length;
      sec.appendChild(lbl);
      DATA.orphan_nodes.forEach(n => sec.appendChild(buildNode(n, 0, false)));
      panel.appendChild(sec);
    }

    const total = count(DATA.tree)+(DATA.orphan_nodes?.length||0);
    if(total === 0){
      const el = document.createElement('div');
      el.style.cssText = 'padding:24px 16px;color:var(--muted);font-size:12px;font-family:var(--mono);line-height:1.6';
      el.innerHTML = '<b style="color:var(--warn)">⚠ No nodes to display.</b><br><br>'
        +'Possible reasons:<br>'
        +'• Root URL domain doesn\'t match HAR entries<br>'
        +'• All entries were filtered as noise<br>'
        +'• Active filter removed all branches<br><br>'
        +'Try clicking <b>Show All</b> to reset the filter.';
      panel.appendChild(el);
    }

    const chip = document.getElementById('countChip');
    chip.textContent = total+' nodes';
    if(FILTER_MODE === 'auth'){ chip.className='stat-chip auth'; chip.textContent='🔐 '+total+' auth nodes'; }
    else if(FILTER_MODE === 'custom'){ chip.className='stat-chip custom'; chip.textContent='🎯 '+total+' matched'; }

    buildMatchPanel();
  } catch(err) {
    panel.innerHTML = '<div style="padding:20px;color:#f85149;font-family:monospace;font-size:12px">'
      +'<b>Tree render error:</b><br>'+err.message+'<br><br>'
      +'<span style="color:#8b949e">Open browser DevTools (F12) → Console for details.</span>'
      +'</div>';
    console.error('HAR Tree init() error:', err);
  }
}

function buildNode(node, depth, expanded){
  const wrap = document.createElement('div');
  wrap.className = 'tree-node';
  wrap.dataset.url  = (node.url||'').toLowerCase();
  wrap.dataset.meth = (node.method||'').toLowerCase();
  wrap.dataset.stat = String(node.status||'');
  wrap.dataset.id   = node.id||'';

  const kids = node.children?.length > 0;
  const isMatch = FILTER_MODE !== 'none' && nodeMatchKws[node.id]?.size > 0;

  const row = document.createElement('div');
  row.className = 'trow' + (isMatch ? ' filter-match' : '');
  row.style.paddingLeft = (12 + depth * 14) + 'px';

  const tog = document.createElement('span');
  tog.className = 'toggle';
  tog.textContent = kids ? (expanded ? '▾' : '▸') : '·';

  const mc = ['GET','POST','PUT','DELETE','PATCH'].includes(node.method) ? 'm'+node.method : 'mOTHER';
  const mbadge = document.createElement('span');
  mbadge.className = 'mbadge '+mc;
  mbadge.textContent = node.method||'?';

  const icon = document.createElement('span');
  icon.style.cssText = 'flex-shrink:0;font-size:11px';
  icon.textContent = {page:'🌐',api:'⚡',redirect:'↪️',websocket:'🔌',sse:'📡'}[node.node_type]||'⚡';

  const url = document.createElement('span');
  url.className = 'nurl';
  const qs = node.request?.url?.includes('?') ? '?'+node.request.url.split('?').slice(1).join('?') : '';
  const disp = (node.path||'/') + (qs.length > 55 ? qs.substring(0,55)+'…' : qs);
  url.textContent = disp;
  url.title = node.url;

  const sc = node.status>=500?'s5':node.status>=400?'s4':node.status>=300?'s3':node.status>=200?'s2':'s0';
  const dot = document.createElement('span');
  dot.className = 'sdot '+sc;
  dot.title = node.status+' '+(node.status_text||'');

  row.appendChild(tog); row.appendChild(mbadge); row.appendChild(icon);
  row.appendChild(url); row.appendChild(dot);

  const ch = document.createElement('div');
  ch.style.display = expanded ? 'block' : 'none';
  if(kids) node.children.forEach(c => ch.appendChild(buildNode(c, depth+1, false)));

  row.addEventListener('click', e => {
    e.stopPropagation();
    if(kids){
      const open = ch.style.display !== 'none';
      ch.style.display = open ? 'none' : 'block';
      tog.textContent = open ? '▸' : '▾';
    }
    selectRow(row, node);
  });

  nodeRowMap[node.id]  = { row, childWrap: ch, toggle: tog, depth };
  nodeDataMap[node.id] = node;

  wrap.appendChild(row); wrap.appendChild(ch);
  return wrap;
}

/* ── Select a row (centralised) ───────────────────────────────────────────── */
function selectRow(row, node){
  document.querySelectorAll('.trow.selected').forEach(r => r.classList.remove('selected'));
  row.classList.add('selected');
  activeNode   = node;
  activeNodeId = node.id;
  const kws = nodeMatchKws[node.id] || new Set();
  renderDetail(node, kws);

  // Highlight corresponding match button
  if(activeMatchBtn){ activeMatchBtn.classList.remove('active'); activeMatchBtn = null; }
}

/* ── Jump to node by id (from match panel button) ─────────────────────────── */
function jumpToNode(nodeId, matchBtn){
  const entry = nodeRowMap[nodeId];
  if(!entry) return;
  const { row, childWrap, toggle } = entry;

  // Expand all ancestor tree-nodes
  let el = row.parentElement;   // .tree-node
  while(el){
    if(el.classList.contains('tree-node')){
      const wrap = el.querySelector(':scope > div:last-child');
      if(wrap && wrap.style.display === 'none'){
        wrap.style.display = 'block';
        const t = el.querySelector(':scope > .trow .toggle');
        if(t && t.textContent === '▸') t.textContent = '▾';
      }
    }
    el = el.parentElement;
  }

  // Scroll to row
  row.scrollIntoView({ behavior: 'smooth', block: 'center' });

  // Select
  const node = nodeDataMap[nodeId];
  if(node) selectRow(row, node);

  // Highlight button
  if(activeMatchBtn) activeMatchBtn.classList.remove('active');
  if(matchBtn){ matchBtn.classList.add('active'); activeMatchBtn = matchBtn; }
}

/* ── Detail ────────────────────────────────────────────────────────────────── */
function renderDetail(n, highlights){
  const p = document.getElementById('detailPanel');
  const sc = n.status>=500?'var(--danger)':n.status>=400?'var(--danger)':n.status>=300?'var(--warn)':'var(--success)';
  const tc = {page:'ppage',api:'papi',redirect:'predir',websocket:'pws',sse:'pws'}[n.node_type]||'papi';
  const kws = highlights || new Set();

  p.innerHTML = `
    <div class="dheader">
      <div class="durl">${hesc(n.url, kws)}</div>
      <div class="dmeta">
        <span class="mbadge m${n.method}">${esc(n.method)}</span>
        <span style="font-family:var(--mono);font-size:12px;color:${sc}">${n.status} ${esc(n.status_text||'')}</span>
        <span class="pill ${tc}">${esc(n.node_type)}</span>
        ${n.source_har?`<span style="font-family:var(--mono);font-size:10px;color:var(--muted)">${esc(n.source_har)}</span>`:''}
        ${n.timing?.total_ms?`<span style="font-family:var(--mono);font-size:11px;color:var(--muted)">${n.timing.total_ms.toFixed(1)}ms</span>`:''}
        ${kws.size?`<span style="font-family:var(--mono);font-size:10px;padding:2px 8px;border-radius:10px;background:rgba(240,136,62,.12);border:1px solid rgba(240,136,62,.3);color:var(--auth)">🔑 ${kws.size} kw match</span>`:''}
      </div>
    </div>
    <div class="copy-bar">
      <button class="cbtn" id="cpNode" onclick="cpJson()">⎘ Copy Node JSON</button>
      <button class="cbtn" onclick="cpUrl()">⎘ Copy URL</button>
      <button class="cbtn" onclick="cpCurl()">⎘ cURL</button>
    </div>
    <div>
      ${sec('Request Headers', hdrsTable(n.request?.headers||[], kws), true)}
      ${n.request?.cookies?.length ? sec('Request Cookies', cookieTable(n.request.cookies, kws)) : ''}
      ${Object.keys(n.request?.query_params||{}).length ? sec('Query Params', kvTableH(n.request.query_params, kws)) : ''}
      ${n.request?.body ? sec('Request Body', bodyBlock(n.request.body, n.request.body_parsed, kws, n.request.body_mime_type||"")) : ''}
      ${sec('Response Headers', hdrsTable(n.response?.headers||[], kws), true)}
      ${n.response?.cookies?.length ? sec('Response Cookies', cookieTable(n.response.cookies, kws)) : ''}
      ${n.response?.redirect_url ? sec('Redirect →', `<p style="font-family:var(--mono);font-size:12px;color:var(--warn);word-break:break-all">${hesc(n.response.redirect_url, kws)}</p>`) : ''}
      ${n.response?.body ? sec('Response Body', bodyBlock(n.response.body, n.response.body_parsed, kws, n.response.body_mime_type||"")) : ''}
      ${n.timing?.total_ms ? sec('Timing', timingBlock(n.timing)) : ''}
      ${n.children?.length ? sec('Children ('+n.children.length+')', childrenTable(n.children)) : ''}
    </div>`;

  p.querySelectorAll('.sec-h').forEach(h => {
    h.addEventListener('click', () => {
      const b = h.nextElementSibling;
      b.classList.toggle('open');
      h.querySelector('.chev').textContent = b.classList.contains('open') ? '▾' : '▸';
    });
  });
}

function sec(title, content, open=false){
  return `<div class="sec">
    <div class="sec-h"><span>${esc(title)}</span><span class="chev">${open?'▾':'▸'}</span></div>
    <div class="sec-body${open?' open':''}">${content}</div>
  </div>`;
}
function hdrsTable(hs, kws=new Set()){
  if(!hs?.length) return '<p class="no-data">—</p>';
  return `<table class="kv">${hs.map(h=>{
    const vEnc = (h.value||'').length>16 ? detectEncodings(h.value||'') : [];
    const badges = vEnc.map(id=>{const e=ENCODINGS.find(e=>e.id===id);return`<span class="enc-badge ${e.cls}">${e.badge}</span>`;}).join('');
    return `<tr><td>${hesc(h.name,kws)}</td><td>${hesc(h.value,kws)}${badges}</td></tr>`;
  }).join('')}</table>`;
}
function cookieTable(cs, kws=new Set()){
  return `<table class="kv">${cs.map(c=>{
    const vEnc=(c.value||'').length>16?detectEncodings(c.value||''):[];
    const badges=vEnc.map(id=>{const e=ENCODINGS.find(e=>e.id===id);return`<span class="enc-badge ${e.cls}">${e.badge}</span>`;}).join('');
    return `<tr><td>${hesc(c.name,kws)}</td><td>${hesc(c.value,kws)}${badges}${c.http_only?' <span style="color:var(--muted);font-size:9px">HttpOnly</span>':''}${c.secure?' <span style="color:var(--muted);font-size:9px">Secure</span>':''}</td></tr>`;
  }).join('')}</table>`;
}
function kvTableH(obj, kws=new Set()){
  return `<table class="kv">${Object.entries(obj).map(([k,v])=>{
    const sv=Array.isArray(v)?v.join(', '):String(v);
    const vEnc = sv.length>16 ? detectEncodings(sv) : [];
    const badges = vEnc.map(id=>{const e=ENCODINGS.find(e=>e.id===id);return`<span class="enc-badge ${e.cls}">${e.badge}</span>`;}).join('');
    return `<tr><td>${hesc(k,kws)}</td><td>${hesc(sv,kws)}${badges}</td></tr>`;
  }).join('')}</table>`;
}
/* ── Body value decode helper ─────────────────────────────────────────────── */
function _attrEsc(s){
  return String(s).replace(/&/g,'&amp;').replace(/"/g,'&quot;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
}

function _decodeBodyValue(el, method){
  /* Called from badge onclick — reads raw value from data-val attribute. */
  _ensureDecodeUI();
  _selText = el.getAttribute('data-val');
  _decodeHistory = [];
  applyDecode(method, false);
}

function _bodyValueRow(k, v, kws){
  /* For a single key:value pair, return an HTML row that shows the value and
     any detected encodings as inline quick-decode links. */
  const vStr = typeof v === 'string' ? v : JSON.stringify(v);
  const enc  = detectEncodings(vStr);
  let badges = '';
  if(enc.length){
    badges = enc.map(id=>{
      const e=ENCODINGS.find(e=>e.id===id);
      if(!e)return'';
      // Store raw value in data-val attribute (HTML-escaped) to avoid
      // JSON.stringify quote-wrapping that breaks the decoder input.
      return`<span class="enc-badge ${e.cls}" style="cursor:pointer" `+
        `title="Click to decode ${e.label}" `+
        `data-val="${_attrEsc(vStr)}" `+
        `onclick="event.stopPropagation();_decodeBodyValue(this,'${id}')">`+
        `${e.badge} ↗</span>`;
    }).join('');
  }
  const kHtml = `<span style="color:#8b949e">${hesc(k,kws)}</span>`;
  // Long values: show first 120 chars with expand toggle
  const VMAX = 120;
  let vHtml;
  if(vStr.length > VMAX){
    const uid2='bv'+Math.random().toString(36).slice(2);
    vHtml=`<span id="${uid2}-short">${hesc(vStr.substring(0,VMAX),kws)}<span style="color:var(--muted)">…</span>`+
      `<a href="#" style="color:var(--accent);font-size:10px;margin-left:4px" `+
      `onclick="event.preventDefault();document.getElementById('${uid2}-short').style.display='none';`+
      `document.getElementById('${uid2}-full').style.display='inline';return false;">show all</a></span>`+
      `<span id="${uid2}-full" style="display:none">${hesc(vStr,kws)}</span>`;
  } else {
    vHtml = hesc(vStr,kws);
  }
  return `<tr><td style="color:#8b949e;white-space:nowrap;vertical-align:top;padding:3px 8px 3px 0;min-width:120px">${kHtml}</td>`+
    `<td style="word-break:break-all;padding:3px 0;vertical-align:top">${vHtml}${badges?`<span style="margin-left:6px">${badges}</span>`:''}</td></tr>`;
}

function _flattenObj(obj, prefix, rows, kws, depth){
  if(depth>6)return;
  if(typeof obj==='object'&&obj!==null&&!Array.isArray(obj)){
    for(const[k,v] of Object.entries(obj)){
      const fk=prefix?`${prefix}.${k}`:k;
      if(typeof v==='object'&&v!==null){
        _flattenObj(v,fk,rows,kws,depth+1);
      } else {
        rows.push(_bodyValueRow(fk,v,kws));
      }
    }
  } else if(Array.isArray(obj)){
    obj.forEach((item,i)=>_flattenObj(item,`${prefix}[${i}]`,rows,kws,depth+1));
  } else {
    rows.push(_bodyValueRow(prefix,obj,kws));
  }
}

function bodyBlock(raw, parsed, kws=new Set(), mime=""){
  const rawStr = raw||'';
  const PREVIEW = 8192;

  // ── Try to render form body first if mime says so ───────────────────────────
  const isForm = mime.includes('x-www-form-urlencoded') ||
    (!mime.includes('json') && rawStr.includes('=') && rawStr.includes('&') &&
     !rawStr.trimStart().startsWith('{') && !rawStr.trimStart().startsWith('<'));

  // ── Try to render JSON as a smart key→value table ──────────────────────────
  let jsonObj = isForm ? null : parsed;
  if(!jsonObj && !isForm && rawStr.trimStart().startsWith('{')){
    try{ jsonObj=JSON.parse(rawStr); }catch{}
  }
  if(jsonObj && typeof jsonObj==='object'){
    const rows=[];
    _flattenObj(jsonObj,'',rows,kws,0);
    if(rows.length){
      // Also provide a "raw JSON" toggle
      const uid3='bj'+Math.random().toString(36).slice(2);
      const rawTxt = JSON.stringify(jsonObj,null,2);
      return `<div style="margin-bottom:4px;font-size:10px;color:var(--muted)">`+
        `Body — <a href="#" style="color:var(--accent)" onclick="event.preventDefault();`+
        `var t=document.getElementById('${uid3}-tbl');var p=document.getElementById('${uid3}-raw');`+
        `t.style.display=t.style.display==='none'?'':'none';p.style.display=p.style.display==='none'?'':'none';`+
        `return false;">toggle raw</a></div>`+
        `<table id="${uid3}-tbl" style="width:100%;border-collapse:collapse;font-family:var(--mono);font-size:12px">`+
        rows.join('')+`</table>`+
        `<pre id="${uid3}-raw" style="display:none" class="bpre">${hesc(rawTxt,kws)}</pre>`;
    }
  }

  // ── Try to render URL-encoded form body as key→value table ─────────────────
  if(!jsonObj && rawStr.includes('=') && !rawStr.trimStart().startsWith('<')){
    try{
      const pairs=[...new URLSearchParams(rawStr)];
      if(pairs.length>0){
        const rows=[];
        for(const[k,v] of pairs) rows.push(_bodyValueRow(k,v,kws));
        const uid4='bf'+Math.random().toString(36).slice(2);
        const rawTxt=rawStr;
        return `<div style="margin-bottom:4px;font-size:10px;color:var(--muted)">`+
          `Form body (decoded) — <a href="#" style="color:var(--accent)" onclick="event.preventDefault();`+
          `var t=document.getElementById('${uid4}-tbl');var p=document.getElementById('${uid4}-raw');`+
          `t.style.display=t.style.display==='none'?'':'none';p.style.display=p.style.display==='none'?'':'none';`+
          `return false;">toggle raw</a></div>`+
          `<table id="${uid4}-tbl" style="width:100%;border-collapse:collapse;font-family:var(--mono);font-size:12px">`+
          rows.join('')+`</table>`+
          `<pre id="${uid4}-raw" style="display:none" class="bpre">${hesc(rawTxt,kws)}</pre>`;
      }
    }catch{}
  }

  // ── Fallback: plain pre with encode hint + show-more toggle ────────────────
  const rawEnc = detectEncodings(rawStr);
  let hint = '';
  if(rawEnc.length){
    const chips = rawEnc.map(id=>{
      const e=ENCODINGS.find(e=>e.id===id);
      return `<span class="enc-badge ${e.cls}">${e.badge}</span>`;
    }).join('');
    hint = `<div class="enc-hint">${chips}<span>detected — select text to decode</span></div>`;
  }
  const txt = parsed ? JSON.stringify(parsed,null,2) : rawStr;
  if(txt.length <= PREVIEW){
    return hint+`<pre class="bpre">${hesc(txt, kws)}</pre>`;
  }
  const uid = 'bd'+Math.random().toString(36).slice(2);
  return hint+
    `<pre class="bpre" id="${uid}-pre">${hesc(txt.substring(0,PREVIEW), kws)}`+
    `<span id="${uid}-ellipsis" style="color:var(--muted)">…\n[${(txt.length/1024).toFixed(1)} KB total — `+
    `<a href="#" style="color:var(--accent)" onclick="event.preventDefault();`+
    `document.getElementById('${uid}-pre').innerHTML=document.getElementById('${uid}-full').innerHTML;`+
    `document.getElementById('${uid}-ellipsis').remove();document.getElementById('${uid}-full').remove();return false;">`+
    `show all</a>]</span></pre>`+
    `<span id="${uid}-full" style="display:none">${hesc(txt,kws)}</span>`;
}
function timingBlock(t){
  return `<div style="font-family:var(--mono);font-size:12px;display:flex;gap:18px;flex-wrap:wrap">
    <span><span style="color:var(--muted)">Total </span><span style="color:var(--accent2)">${t.total_ms?.toFixed(1)}ms</span></span>
    ${t.wait_ms!=null?`<span><span style="color:var(--muted)">Wait </span>${t.wait_ms?.toFixed(1)}ms</span>`:''}
    ${t.receive_ms!=null?`<span><span style="color:var(--muted)">Recv </span>${t.receive_ms?.toFixed(1)}ms</span>`:''}
    ${t.started_at?`<span><span style="color:var(--muted)">Started </span>${esc(t.started_at)}</span>`:''}
  </div>`;
}
function childrenTable(cs){
  return `<table class="kv">${cs.map(c=>`<tr><td class="mbadge m${c.method}" style="width:auto;padding:1px 5px;margin:1px 0">${esc(c.method)}</td><td><span style="font-family:var(--mono);font-size:11px">${esc(c.path||'/')} <span style="color:var(--muted)">${c.status}</span></span></td></tr>`).join('')}</table>`;
}

/* ── Match panel ────────────────────────────────────────────────────────────── */
let matchBodyCollapsed = false;

function buildMatchPanel(){
  if(!MATCH_INFO || MATCH_INFO.length === 0) return;

  const panel  = document.getElementById('matchPanel');
  const body   = document.getElementById('matchBody');
  const count  = document.getElementById('matchCount');
  panel.classList.remove('hidden');

  // Count total keyword hits
  let totalHits = 0;
  MATCH_INFO.forEach(mi => totalHits += (mi.matches||[]).length);
  count.textContent = `· ${MATCH_INFO.length} nodes · ${totalHits} hits`;

  // Build one button per (node × keyword-match)
  body.innerHTML = '';
  MATCH_INFO.forEach(mi => {
    (mi.matches || []).forEach(m => {
      const btn = document.createElement('button');
      btn.className = 'mkw-btn';
      btn.title = `${m.actual || m.keyword}\n\nField: ${m.field}\nNode: ${mi.url}`;
      btn.innerHTML =
        `<span class="mkw-kw">${esc(m.keyword)}</span>`+
        `<span class="mkw-field">${esc(m.field)}</span>`+
        `<span class="mkw-path">${esc(mi.method)} ${esc(mi.path)}</span>`;
      btn.addEventListener('click', () => jumpToNode(mi.node_id, btn));
      body.appendChild(btn);
    });
  });
}

function toggleMatchBody(){
  matchBodyCollapsed = !matchBodyCollapsed;
  document.getElementById('matchBody').classList.toggle('collapsed', matchBodyCollapsed);
  document.getElementById('matchChev').textContent = matchBodyCollapsed ? '▸' : '▾';
}

/* ── Search ────────────────────────────────────────────────────────────────── */
function doSearch(q){
  q = q.toLowerCase().trim();
  const nodes = document.querySelectorAll('.tree-node');
  if(!q){ nodes.forEach(n=>n.classList.remove('hidden')); return; }
  nodes.forEach(n=>{
    const m = n.dataset.url?.includes(q)||n.dataset.meth?.includes(q)||n.dataset.stat?.includes(q);
    n.classList.toggle('hidden',!m);
    if(m){
      let p = n.parentElement?.closest('.tree-node');
      while(p){ p.classList.remove('hidden'); p=p.parentElement?.closest('.tree-node'); }
    }
  });
}

/* ── Expand / Collapse ─────────────────────────────────────────────────────── */
function expandAll(){
  document.querySelectorAll('.tree-node>div:last-child').forEach(c=>c.style.display='block');
  document.querySelectorAll('.toggle').forEach(t=>{if(t.textContent==='▸')t.textContent='▾';});
}
function collapseAll(){
  document.querySelectorAll('.tree-node>div:last-child').forEach(c=>c.style.display='none');
  document.querySelectorAll('.toggle').forEach(t=>{if(t.textContent==='▾')t.textContent='▸';});
}

/* ── Copy helpers ──────────────────────────────────────────────────────────── */
function cpText(text,btnId,label){
  navigator.clipboard.writeText(text).then(()=>{
    if(!btnId) return;
    const b=document.getElementById(btnId);
    if(!b) return;
    const orig=b.textContent;
    b.textContent='✓ '+label;
    b.classList.add('ok');
    setTimeout(()=>{b.textContent=orig;b.classList.remove('ok');},2000);
  });
}
function cpJson(){ if(activeNode) cpText(JSON.stringify(activeNode,null,2),'cpNode','Copied!'); }
function cpUrl(){ if(activeNode) cpText(activeNode.url||'',null,''); }
function cpCurl(){
  if(!activeNode) return;
  const n=activeNode;
  const hdrs=(n.request?.headers||[]).map(h=>`-H '${h.name}: ${h.value}'`).join(' ');
  const body=n.request?.body?`-d '${(n.request.body||'').replace(/'/g,"'\\''")}' `:'';
  const cmd=`curl -X ${n.method} '${n.url}' ${hdrs} ${body}`.trim();
  cpText(cmd,'cpNode','Copied cURL!');
}
function copyAll(){
  cpText(JSON.stringify(DATA,null,2),null,'');
  const b=document.querySelector('.tbtn[onclick="copyAll()"]');
  if(b){const o=b.textContent;b.textContent='✓ Copied';setTimeout(()=>b.textContent=o,2000);}
}

/* ── String helpers ────────────────────────────────────────────────────────── */
function esc(s){
  return String(s??'').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
}

/**
 * Escape `s` and then wrap every occurrence of each keyword in <mark class="kw-hl">.
 * `kws` can be a Set or Array of lowercase keyword strings.
 */
function hesc(s, kws){
  let out = esc(s);
  if(!kws || kws.size === 0 || kws.length === 0) return out;
  const kwArr = kws instanceof Set ? [...kws] : kws;
  // Sort longest-first to avoid partial clobbering
  const sorted = kwArr.slice().sort((a,b)=>b.length-a.length);
  for(const kw of sorted){
    if(!kw) continue;
    // kw is already lowercased; build case-insensitive regex on its escaped form
    const ek = esc(kw).replace(/[.*+?^${}()|[\]\\]/g,'\\$&');
    try {
      const re = new RegExp(ek, 'gi');
      out = out.replace(re, m => `<mark class="kw-hl">${m}</mark>`);
    } catch(e){}
  }
  return out;
}

/* ── Encoding detection & decode system ─────────────────────────────────── */
const ENCODINGS=[
  {id:'params',label:'URL Params Extract',badge:'KEY=VAL',cls:'enc-url',
   detect:t=>{const s=t.trim();return s.includes('=')&&s.includes('&')&&!/[\s<>{}]/.test(s)},
   decode:t=>{
     try{
       const s=t.trim().replace(/^\?/,'');
       const pairs=s.split('&').filter(p=>p.includes('='));
       if(!pairs.length)return{ok:0,val:'No key=value pairs found'};
       const rows=pairs.map(p=>{
         const eq=p.indexOf('=');const k=p.slice(0,eq);const v=p.slice(eq+1);
         let dec='';try{dec=decodeURIComponent(v.replace(/\+/g,' '));}catch{dec=v;}
         const further=detectEncodings(dec);
         const hint=further.length?' [\u2192 '+further.map(id=>{const e=ENCODINGS.find(e=>e.id===id);return e?e.badge:id;}).join(',')+']':'';
         return k+' =\n  raw:     '+v+'\n  decoded: '+dec+hint;
       });
       return{ok:1,val:rows.join('\n\n')};
     }catch(e){return{ok:0,val:''+e};}
   }},
  {id:'url',  label:'URL Decode',         badge:'URL%',  cls:'enc-url',
   detect:t=>/%[0-9A-Fa-f]{2}/.test(t),
   decode:t=>{try{return{ok:1,val:decodeURIComponent(t.replace(/\+/g,' '))}}catch(e){return{ok:0,val:''+e}}}},
  {id:'durl', label:'Double URL Decode',  badge:'URL%%', cls:'enc-url',
   detect:t=>/%25[0-9A-Fa-f]{2}/.test(t),
   decode:t=>{try{const a=decodeURIComponent(t.replace(/\+/g,' '));return{ok:1,val:decodeURIComponent(a.replace(/\+/g,' '))}}catch(e){return{ok:0,val:''+e}}}},
  {id:'jwt',  label:'JWT Decode',         badge:'JWT',   cls:'enc-jwt',
   detect:t=>{const p=t.trim().split('.');return p.length===3&&p.every(s=>/^[A-Za-z0-9_-]+$/.test(s)&&s.length>=10)&&p[0].length+p[1].length+p[2].length>=60;},
   decode:t=>{try{const p=t.trim().split('.');const d=s=>{s=s.replace(/-/g,'+').replace(/_/g,'/');while(s.length%4)s+='=';return JSON.parse(atob(s))};return{ok:1,val:JSON.stringify({header:d(p[0]),payload:d(p[1])},null,2)+'\n\n[signature omitted]'}}catch(e){return{ok:0,val:''+e}}}},
  {id:'b64',  label:'Base64 Decode',      badge:'B64',   cls:'enc-b64',
   detect:t=>{const s=t.trim().replace(/\s/g,'');if(s.length<20||!/^[A-Za-z0-9+\/]+=*$/.test(s))return false;const hasTypicalB64=(s.includes('+')||s.includes('/')||s.includes('='));const padded=s.length%4===0||(s.length+1)%4===0||(s.length+2)%4===0;return padded&&(hasTypicalB64||s.length>=60);},
   decode:t=>{try{const b=atob(t.trim().replace(/\s/g,''));try{const u=new TextDecoder('utf-8',{fatal:true}).decode(Uint8Array.from(b,c=>c.charCodeAt(0)));try{return{ok:1,val:JSON.stringify(JSON.parse(u),null,2)}}catch{return{ok:1,val:u}}}catch{return{ok:1,val:'[binary]\n'+[...b].map(c=>c.charCodeAt(0).toString(16).padStart(2,'0')).join(' ')}}}catch(e){return{ok:0,val:''+e}}}},
  {id:'b64u', label:'Base64URL Decode',   badge:'B64U',  cls:'enc-b64',
   detect:t=>{const s=t.trim();if(s.length<20||!/^[A-Za-z0-9_-]+=*$/.test(s))return false;return(s.includes('-')||s.includes('_'))&&s.length>=40&&!s.includes('.')},
   decode:t=>{try{let s=t.trim().replace(/-/g,'+').replace(/_/g,'/');while(s.length%4)s+='=';const b=atob(s);try{const u=new TextDecoder('utf-8',{fatal:true}).decode(Uint8Array.from(b,c=>c.charCodeAt(0)));try{return{ok:1,val:JSON.stringify(JSON.parse(u),null,2)}}catch{return{ok:1,val:u}}}catch{return{ok:1,val:'[binary]\n'+[...b].map(c=>c.charCodeAt(0).toString(16).padStart(2,'0')).join(' ')}}}catch(e){return{ok:0,val:''+e}}}},
  {id:'html', label:'HTML Entity Decode', badge:'HTML&', cls:'enc-html',
   detect:t=>/(&amp;|&lt;|&gt;|&quot;|&#\d+;|&[a-z]{2,6};)/.test(t),
   decode:t=>{try{const e=document.createElement('div');e.innerHTML=t;return{ok:1,val:e.textContent}}catch(e){return{ok:0,val:''+e}}}},
  {id:'hex',  label:'Hex Decode',         badge:'0x',    cls:'enc-hex',
   detect:t=>{const s=t.trim().replace(/\s/g,'').replace(/^0x/i,'');return s.length>=16&&s.length%2===0&&/^[0-9a-fA-F]+$/.test(s)},
   decode:t=>{try{const s=t.trim().replace(/\s/g,'').replace(/^0x/i,'');const b=[];for(let i=0;i<s.length;i+=2)b.push(parseInt(s.substr(i,2),16));return{ok:1,val:new TextDecoder().decode(new Uint8Array(b))}}catch(e){return{ok:0,val:''+e}}}},
  {id:'xml',  label:'XML Pretty Print',   badge:'XML',   cls:'enc-html',
   detect:t=>{const s=t.trim();return s.startsWith('<')&&s.includes('>')&&(s.includes('</')||s.includes('/>'))},
   decode:t=>{
     try{
       const parser=new DOMParser();
       const doc=parser.parseFromString(t.trim(),'application/xml');
       const err=doc.querySelector('parsererror');
       if(err)return{ok:0,val:'XML parse error:\n'+err.textContent};
       const xs=new XMLSerializer();
       try{
         const xsltDoc=parser.parseFromString('<xsl:stylesheet xmlns:xsl="http://www.w3.org/1999/XSL/Transform"><xsl:strip-space elements="*"/><xsl:output method="xml" indent="yes"/><xsl:template match="node()|@*"><xsl:copy><xsl:apply-templates select="node()|@*"/></xsl:copy></xsl:template></xsl:stylesheet>','application/xml');
         const xp=new XSLTProcessor();xp.importStylesheet(xsltDoc);
         const out=xp.transformToDocument(doc);
         return{ok:1,val:xs.serializeToString(out).replace(/^<\?xml[^?]*\?>\s*/,'')};
       }catch{return{ok:1,val:xs.serializeToString(doc)};}
     }catch(e){return{ok:0,val:''+e};}
   }},
];

function detectEncodings(t){
  if(!t||t.trim().length<5)return[];
  const s=t.trim();
  return ENCODINGS.filter(e=>{try{return e.detect(s)}catch{return false}}).map(e=>e.id);
}

/* ── Decode popup ─────────────────────────────────────────────────────────── */
let _selText='';

function _ensureDecodeUI(){
  if(document.getElementById('decodePopup'))return;
  const pp=document.createElement('div');
  pp.id='decodePopup';pp.className='decode-popup';
  pp.innerHTML=
    '<button class="decode-close" onclick="hideDecodePopup()">✕</button>'+
    '<div class="decode-popup-title">🔍 Decode Selection</div>'+
    '<div id="decDetected" style="margin-bottom:7px"></div>'+
    '<div style="font-size:10px;color:var(--muted);margin-bottom:4px">All options:</div>'+
    '<div class="decode-opts" id="decOpts"></div>';
  document.body.appendChild(pp);
  const rp=document.createElement('div');
  rp.id='decodeResult';rp.className='decode-result-panel';
  rp.innerHTML=
    '<div class="decode-result-header">'+
    '<span id="decResTitle">Decoded result</span>'+
    '<button class="decode-close" onclick="hideDecodeResult()">✕</button></div>'+
    '<div id="decBreadcrumb" style="display:none;font-size:10px;color:var(--muted);padding:3px 0 5px;flex-wrap:wrap;gap:3px;align-items:center"></div>'+
    '<pre class="decode-result-body" id="decResBody"></pre>'+
    '<div id="decChain" style="display:none;padding:4px 0;border-top:1px solid var(--border);margin-top:4px">'+
    '<div style="font-size:10px;color:var(--muted);margin-bottom:4px">Decode further \u2192</div>'+
    '<div class="decode-opts" id="decChainOpts"></div></div>'+
    '<div class="decode-result-actions">'+
    '<button class="decode-ra-btn" id="cpDecBtn" onclick="cpDecoded()">&#x2398; Copy</button>'+
    '<button class="decode-ra-btn" id="decRevertBtn" onclick="revertDecode()" style="display:none">\u21a9 Revert</button>'+
    '<button class="decode-ra-btn" onclick="hideDecodeResult();hideDecodePopup()">&#x2715; Close</button></div>';
  document.body.appendChild(rp);
}
function showDecodePopup(x,y,text){
  _ensureDecodeUI();
  _selText=text;
  const detected=detectEncodings(text);
  const dd=document.getElementById('decDetected');
  if(detected.length){
    dd.innerHTML='<div style="font-size:10px;color:var(--muted);margin-bottom:4px">Auto-detected:</div>'+
      detected.map(id=>{
        const e=ENCODINGS.find(e=>e.id===id);
        return `<span class="enc-badge ${e.cls}" style="cursor:pointer;margin-bottom:3px" onclick="applyDecode('${id}')">${e.badge} — ${e.label}</span>`;
      }).join('');
  } else {
    dd.innerHTML='<span style="font-size:10px;color:var(--muted)">No encoding detected — try manually:</span>';
  }
  document.getElementById('decOpts').innerHTML=
    ENCODINGS.map(e=>`<button class="decode-btn${detected.includes(e.id)?' detected':''}" onclick="applyDecode('${e.id}')">${e.label}</button>`).join('');
  const popup=document.getElementById('decodePopup');
  popup.classList.add('visible');
  const pw=280,ph=220;
  let px=x,py=y+14;
  if(px+pw>window.innerWidth-10)px=window.innerWidth-pw-10;
  if(py+ph>window.innerHeight-10)py=y-ph-10;
  popup.style.left=px+'px';popup.style.top=py+'px';
}

function hideDecodePopup(){
  const p=document.getElementById('decodePopup');if(p)p.classList.remove('visible');
}
function hideDecodeResult(){
  const r=document.getElementById('decodeResult');if(r)r.classList.remove('visible');
}

function applyDecode(method, fromChain){
  const enc=ENCODINGS.find(e=>e.id===method);
  if(!enc)return;
  const inputText=fromChain ? document.getElementById('decResBody').textContent : _selText;
  if(!inputText)return;

  if(fromChain){
    const prevText=document.getElementById('decResBody').textContent;
    const prevTitle=document.getElementById('decResTitle').textContent;
    if(prevText) _decodeHistory.push({label:prevTitle,text:prevText});
  } else {
    _decodeHistory=[];
  }

  const res=enc.decode(inputText);
  document.getElementById('decResTitle').textContent=enc.label+(res.ok?' \u2713':' \u26a0 Error');
  document.getElementById('decResBody').textContent=res.val;
  _updateBreadcrumb(enc.label);
  _updateChain(res.ok ? res.val : '');

  const popup=document.getElementById('decodePopup');
  const rect=popup.getBoundingClientRect();
  const r=document.getElementById('decodeResult');
  const rw=Math.min(480,window.innerWidth-20);
  let rx=rect.left,ry=rect.bottom+8;
  if(rx+rw>window.innerWidth-10)rx=Math.max(5,window.innerWidth-rw-10);
  if(ry+320>window.innerHeight-10)ry=Math.max(5,rect.top-320-8);
  r.style.left=rx+'px';r.style.top=ry+'px';r.style.width=rw+'px';
  r.classList.add('visible');
  document.getElementById('decRevertBtn').style.display=_decodeHistory.length?'':'none';
}

function _updateBreadcrumb(currentLabel){
  const bc=document.getElementById('decBreadcrumb');
  if(!bc)return;
  if(!_decodeHistory.length){bc.style.display='none';bc.innerHTML='';return;}
  bc.style.display='flex';
  bc.innerHTML=_decodeHistory.map((h,i)=>
    `<span style="cursor:pointer;color:var(--accent);text-decoration:underline" onclick="_jumpHistory(${i})">${h.label}</span>`+
    `<span style="color:var(--border);margin:0 2px"> \u203a </span>`
  ).join('')+`<span style="color:var(--text)">${currentLabel}</span>`;
}

function _jumpHistory(idx){
  const entry=_decodeHistory[idx];
  if(!entry)return;
  document.getElementById('decResBody').textContent=entry.text;
  document.getElementById('decResTitle').textContent=entry.label;
  _decodeHistory=_decodeHistory.slice(0,idx);
  _updateBreadcrumb(entry.label);
  _updateChain(entry.text);
  document.getElementById('decRevertBtn').style.display=_decodeHistory.length?'':'none';
}

function _updateChain(resultText){
  const chain=document.getElementById('decChain');
  const opts=document.getElementById('decChainOpts');
  if(!chain||!opts)return;
  // Auto-detect so we can highlight suggested decoders, but always show ALL
  const detected=detectEncodings(resultText);
  if(resultText.trim().startsWith('<')&&!detected.includes('xml'))detected.push('xml');
  chain.style.display='block';
  opts.innerHTML=ENCODINGS.map(e=>{
    const isDetected=detected.includes(e.id);
    return`<button class="decode-btn${isDetected?' detected':''}" title="${isDetected?'Auto-detected':''}" onclick="applyDecode('${e.id}',true)">${e.label}${isDetected?' ✦':''}</button>`;
  }).join('');
}
function cpDecoded(){
  const b=document.getElementById('decResBody');if(!b)return;
  navigator.clipboard.writeText(b.textContent).then(()=>{
    const btn=document.getElementById('cpDecBtn');
    if(btn){const o=btn.textContent;btn.textContent='✓ Copied';btn.classList.add('ok');
      setTimeout(()=>{btn.textContent=o;btn.classList.remove('ok')},2000);}
  });
}
function revertDecode(){
  if(_decodeHistory.length){
    const prev=_decodeHistory.pop();
    document.getElementById('decResBody').textContent=prev.text;
    document.getElementById('decResTitle').textContent=prev.label;
    _updateBreadcrumb(prev.label);
    _updateChain(prev.text);
    document.getElementById('decRevertBtn').style.display=_decodeHistory.length?'':'none';
  } else {
    hideDecodeResult(); hideDecodePopup();
  }
}

document.addEventListener('mouseup',e=>{
  if(e.target.closest('#decodePopup')||e.target.closest('#decodeResult'))return;
  const sel=window.getSelection();
  if(!sel||sel.isCollapsed){
    if(!e.target.closest('#decodePopup'))hideDecodePopup();
    return;
  }
  const text=sel.toString().trim();
  if(text.length<5){hideDecodePopup();return;}
  const anchor=sel.anchorNode?.parentElement;
  if(!anchor?.closest('#detailPanel')){hideDecodePopup();return;}
  showDecodePopup(e.clientX,e.clientY,text);
});
document.addEventListener('keydown',e=>{
  if(e.key==='Escape'){hideDecodePopup();hideDecodeResult();}
});

/* ── Init ──────────────────────────────────────────────────────────────────── */
init();
</script>
</body>
</html>"""