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

MAX_BODY_CHARS = 4_000


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
      ${n.request?.body ? sec('Request Body', bodyBlock(n.request.body, n.request.body_parsed, kws)) : ''}
      ${sec('Response Headers', hdrsTable(n.response?.headers||[], kws), true)}
      ${n.response?.cookies?.length ? sec('Response Cookies', cookieTable(n.response.cookies, kws)) : ''}
      ${n.response?.redirect_url ? sec('Redirect →', `<p style="font-family:var(--mono);font-size:12px;color:var(--warn);word-break:break-all">${hesc(n.response.redirect_url, kws)}</p>`) : ''}
      ${n.response?.body ? sec('Response Body', bodyBlock(n.response.body, n.response.body_parsed, kws)) : ''}
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
  return `<table class="kv">${hs.map(h=>`<tr><td>${hesc(h.name,kws)}</td><td>${hesc(h.value,kws)}</td></tr>`).join('')}</table>`;
}
function cookieTable(cs, kws=new Set()){
  return `<table class="kv">${cs.map(c=>`<tr><td>${hesc(c.name,kws)}</td><td>${hesc(c.value,kws)}${c.http_only?' <span style="color:var(--muted);font-size:9px">HttpOnly</span>':''}${c.secure?' <span style="color:var(--muted);font-size:9px">Secure</span>':''}</td></tr>`).join('')}</table>`;
}
function kvTableH(obj, kws=new Set()){
  return `<table class="kv">${Object.entries(obj).map(([k,v])=>`<tr><td>${hesc(k,kws)}</td><td>${hesc(Array.isArray(v)?v.join(', '):String(v),kws)}</td></tr>`).join('')}</table>`;
}
function bodyBlock(raw, parsed, kws=new Set()){
  const txt = parsed ? JSON.stringify(parsed,null,2) : (raw||'');
  return `<pre class="bpre">${hesc(txt.substring(0,8192), kws)}</pre>`;
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

/* ── Init ──────────────────────────────────────────────────────────────────── */
init();
</script>
</body>
</html>"""
