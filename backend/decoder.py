"""
decoder.py
──────────
Smart multi-layer body and header value decoder.

Used at HAR ingestion time (har_processor.py) to pre-expand all encoded
content into searchable plaintext that is stored permanently on each
RequestNode.  Keyword filters then operate on the decoded text with zero
runtime overhead.

Decoding pipeline (applied recursively until no new content is found):
  1. URL-encoded form  key=value&key=value  (handles SAMLResponse=, JWT=, nested JSON=)
  2. JSON object       {"key": "value"}     (recursive, depth-limited)
  3. JWT               header.payload.sig   (header+payload claims extracted as text)
  4. Base64 / Base64URL                     (decodes to XML, JSON, plain text, binary)
  5. HTML entities     &amp; &lt; &#60;
  6. Hex strings       deadbeef…
  7. XML pretty-print                       (keeps decoded XML readable for keyword match)

The result is a single concatenated string that contains:
  - The original raw value
  - Every useful decoded layer
  - All nested keys and values found within decoded content

This string is stored in RequestDetail.body_decoded and
ResponseDetail.body_decoded.  The original body field is untouched.
"""
from __future__ import annotations

import base64
import html as _html_mod
import json as _json
import re
from typing import List
from urllib.parse import parse_qsl, unquote

# ── Regex anchors ─────────────────────────────────────────────────────────────
_B64_RE     = re.compile(r'^[A-Za-z0-9+/]+=*$')
_B64URL_RE  = re.compile(r'^[A-Za-z0-9_-]+=*$')
_HEX_RE     = re.compile(r'^[0-9a-fA-F]+$')
_ENTITY_RE  = re.compile(r'&(?:amp|lt|gt|quot|apos|#[0-9]+|#x[0-9a-fA-F]+);')
_PCT_RE     = re.compile(r'%[0-9A-Fa-f]{2}')   # URL-encoded bytes


# ── Low-level decode attempts ─────────────────────────────────────────────────

def _try_url(s: str) -> str:
    """URL-decode %XX sequences only (not + → space — that's context-dependent)."""
    if not _PCT_RE.search(s):
        return ''
    try:
        dec = unquote(s)
        return dec if dec != s else ''
    except Exception:
        return ''


def _try_b64(s: str) -> str:
    """Base64 or Base64URL decode.  Returns decoded UTF-8 text or ''."""
    s = s.strip()
    if len(s) < 20:
        return ''
    # Convert Base64URL to standard
    std = s.replace('-', '+').replace('_', '/')
    pad = len(std) % 4
    if pad:
        std += '=' * (4 - pad)
    # Quick alphabet check before attempting decode
    if not _B64_RE.match(std):
        return ''
    try:
        raw = base64.b64decode(std, validate=True)
        return raw.decode('utf-8', errors='replace')
    except Exception:
        try:
            raw = base64.b64decode(std, validate=False)
            return raw.decode('utf-8', errors='replace')
        except Exception:
            return ''


def _try_jwt(s: str) -> str:
    """Decode JWT header+payload claims to a flat key=value string."""
    parts = s.strip().split('.')
    if len(parts) != 3:
        return ''
    if not all(len(p) >= 10 and _B64URL_RE.match(p) for p in parts):
        return ''
    if sum(len(p) for p in parts) < 60:
        return ''
    def _seg(seg: str) -> str:
        seg = seg.replace('-', '+').replace('_', '/')
        pad = len(seg) % 4
        if pad:
            seg += '=' * (4 - pad)
        try:
            return base64.b64decode(seg, validate=True).decode('utf-8', errors='replace')
        except Exception:
            return ''
    hdr  = _seg(parts[0])
    pay  = _seg(parts[1])
    if not hdr or not pay:
        return ''
    combined = hdr + '\n' + pay
    # Also flatten all JSON claims so nested keys are searchable
    for seg_text in (hdr, pay):
        try:
            obj = _json.loads(seg_text)
            if isinstance(obj, dict):
                combined += '\n' + '\n'.join(f"{k}={v}" for k, v in obj.items())
        except Exception:
            pass
    return combined


def _try_html_entities(s: str) -> str:
    if not _ENTITY_RE.search(s):
        return ''
    try:
        return _html_mod.unescape(s)
    except Exception:
        return ''


def _try_hex(s: str) -> str:
    s = s.strip()
    if len(s) < 32 or len(s) % 2 != 0 or not _HEX_RE.match(s):
        return ''
    try:
        return bytes.fromhex(s).decode('utf-8', errors='replace')
    except Exception:
        return ''


# ── Recursive value expander ───────────────────────────────────────────────────

def _expand_value(v: str, depth: int = 0) -> List[str]:
    """
    Try all decode layers on a single string value.
    Returns list of new decoded strings (not including the original).
    Recurses into decoded results up to depth 4.
    """
    if depth > 4 or not v or len(v) < 4:
        return []

    results: List[str] = []
    seen: set = set()

    def _add(t: str):
        t = t.strip()
        if t and t != v and t not in seen:
            seen.add(t)
            results.append(t)
            # Recurse: decoded content may itself be encoded
            for sub in _expand_value(t, depth + 1):
                if sub not in seen:
                    seen.add(sub)
                    results.append(sub)

    # Try JWT first (has dots — would be misidentified by URL decoder)
    _add(_try_jwt(v))

    # URL decode (%XX only — preserves + as literal)
    url_dec = _try_url(v)
    if url_dec:
        _add(url_dec)
        # Also try Base64 on URL-decoded result
        _add(_try_b64(url_dec))
        _add(_try_jwt(url_dec))

    # Base64 on original value
    _add(_try_b64(v))

    # HTML entities
    _add(_try_html_entities(v))

    # Hex
    _add(_try_hex(v))

    return results


# ── Body expander ─────────────────────────────────────────────────────────────

def _expand_json_obj(obj, parts: List[str], depth: int = 0):
    """Recursively walk a parsed JSON object and expand every string value."""
    if depth > 6:
        return
    if isinstance(obj, dict):
        for k, v in obj.items():
            sv = str(v) if not isinstance(v, (dict, list)) else ''
            if sv:
                parts.append(f"{k}={sv}")
                parts.append(sv)
                for dec in _expand_value(sv):
                    parts.append(f"{k}={dec}")
                    parts.append(dec)
            if isinstance(v, (dict, list)):
                _expand_json_obj(v, parts, depth + 1)
    elif isinstance(obj, list):
        for item in obj:
            _expand_json_obj(item, parts, depth + 1)


def expand_body(raw: str | None, parsed=None) -> str:
    """
    Full body expansion pipeline.  Returns a single concatenated string
    containing the original body plus every decoded layer.

    raw    — the raw body string as stored in the HAR
    parsed — already-parsed Python object (dict/list) if available

    Format detection order:
      A. URL-encoded form  (key=value&key=value)
      B. JSON              ({"key":"value"})
      C. Whole-body Base64 (plain b64 blob)
      D. JWT               (3-part dot-separated)
      E. XML               (kept as-is; XML Pretty Print is display-only)
    """
    parts: List[str] = []

    if raw:
        parts.append(raw)

    stripped = (raw or '').strip().lstrip('?')

    # ── A. URL-encoded form body ──────────────────────────────────────────────
    if (stripped and '=' in stripped
            and not stripped.startswith('{')
            and not stripped.startswith('<')
            and len(stripped) < 2_000_000):
        try:
            # Use parse_qsl which URL-decodes %XX and + → space for form data
            pairs = parse_qsl(stripped, keep_blank_values=True, strict_parsing=False)
            if pairs:
                for k, v in pairs:
                    parts.append(f"{k}={v}")
                    parts.append(v)
                    for dec in _expand_value(v):
                        parts.append(f"{k}={dec}")
                        parts.append(dec)
        except Exception:
            pass

    # ── B. JSON body ──────────────────────────────────────────────────────────
    json_obj = parsed
    if json_obj is None and stripped.startswith('{'):
        try:
            json_obj = _json.loads(stripped)
        except Exception:
            pass
    if json_obj and isinstance(json_obj, (dict, list)):
        _expand_json_obj(json_obj, parts)

    # ── C. Whole-body Base64 ──────────────────────────────────────────────────
    if stripped and not stripped.startswith('<') and not stripped.startswith('{'):
        b64_dec = _try_b64(stripped)
        if b64_dec:
            parts.append(b64_dec)
            # Re-expand the decoded result
            inner = b64_dec.strip()
            if inner.startswith('<') or inner.startswith('{') or '=' in inner:
                for sub in _expand_value(inner):
                    parts.append(sub)
            # Also try JSON parse of decoded content
            if inner.startswith('{'):
                try:
                    obj2 = _json.loads(inner)
                    _expand_json_obj(obj2, parts)
                except Exception:
                    pass

    # ── D. JWT (whole body) ───────────────────────────────────────────────────
    j = _try_jwt(stripped)
    if j:
        parts.append(j)

    # Deduplicate while preserving order
    seen: set = set()
    deduped: List[str] = []
    for p in parts:
        if p and p not in seen:
            seen.add(p)
            deduped.append(p)

    return '\n'.join(deduped)


def expand_header_value(v: str) -> str:
    """
    Expand a single header value.
    Returns original + all decoded layers concatenated.
    Only applied to values >= 16 chars to avoid noise.
    """
    if not v or len(v) < 16:
        return v
    extra = _expand_value(v)
    if not extra:
        return v
    return v + '\n' + '\n'.join(extra)


def expand_headers(headers) -> str:
    """
    Return a searchable string of all header names and decoded values.
    headers is a list of HeaderEntry objects (with .name and .value).
    """
    parts = []
    for h in headers:
        parts.append(f"{h.name}: {h.value}")
        expanded = expand_header_value(h.value)
        if expanded != h.value:
            parts.append(f"{h.name}: {expanded}")
    return '\n'.join(parts)