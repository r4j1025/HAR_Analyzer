from __future__ import annotations
from typing import Any, Dict, List, Literal, Optional, Union
from pydantic import BaseModel, Field


class HeaderEntry(BaseModel):
    name: str
    value: str


class CookieEntry(BaseModel):
    name: str
    value: str
    domain: Optional[str] = None
    path: Optional[str] = None
    expires: Optional[str] = None
    http_only: Optional[bool] = None
    secure: Optional[bool] = None
    same_site: Optional[str] = None


class RequestDetail(BaseModel):
    method: str
    url: str
    http_version: str = "HTTP/1.1"
    headers: List[HeaderEntry] = []
    cookies: List[CookieEntry] = []
    query_params: Dict[str, Any] = {}
    body: Optional[str] = None
    body_mime_type: Optional[str] = None
    body_parsed: Optional[Any] = None
    body_decoded: Optional[str] = None   # all decoded layers, pre-expanded at ingestion
    headers_decoded: Optional[str] = None  # header values expanded


class ResponseDetail(BaseModel):
    status: int
    status_text: str
    headers: List[HeaderEntry] = []
    cookies: List[CookieEntry] = []
    body: Optional[str] = None
    body_mime_type: Optional[str] = None
    body_parsed: Optional[Any] = None
    redirect_url: Optional[str] = None
    body_decoded: Optional[str] = None   # all decoded layers, pre-expanded at ingestion
    headers_decoded: Optional[str] = None  # header values expanded


class TimingInfo(BaseModel):
    started_at: Optional[str] = None
    total_ms: Optional[float] = None
    wait_ms: Optional[float] = None
    receive_ms: Optional[float] = None


class RequestNode(BaseModel):
    id: str
    url: str
    domain: str
    path: str
    method: str
    status: int
    status_text: str
    node_type: str = "api"
    request: RequestDetail
    response: ResponseDetail
    timing: TimingInfo = Field(default_factory=TimingInfo)
    source_har: Optional[str] = None
    children: List[RequestNode] = []
    depth: int = 0


RequestNode.model_rebuild()


class AnalyzeResponse(BaseModel):
    root_url: str
    har_files: List[str]
    total_entries_raw: int
    total_entries_filtered: int
    noise_removed: int
    tree: RequestNode
    orphan_nodes: List[RequestNode] = []
    summary: Dict[str, Any] = {}


class FilterStats(BaseModel):
    total_raw: int
    after_noise_filter: int
    noise_types: Dict[str, int]


# ── Custom Filter ──────────────────────────────────────────────────────────────

class CombinationEntry(BaseModel):
    """
    A combination defines a multi-field signal that should appear together
    in a branch (root → node path).  All non-empty keyword lists must be
    satisfied (field-specific, case-insensitive).

    100 % → "Found"   |   1–99 % → "Partial"   |   0 % → "Not found"
    """
    name: str = "Combination"
    description: Optional[str] = None
    url_keywords: List[str] = Field(default_factory=list)
    req_header_keywords: List[str] = Field(default_factory=list)
    res_header_keywords: List[str] = Field(default_factory=list)
    req_body_keywords: List[str] = Field(default_factory=list)
    res_body_keywords: List[str] = Field(default_factory=list)


class CustomFilterConfig(BaseModel):
    """
    Configuration for the custom keyword filter.

    match_mode = "any_field":
        A node matches if ANY keyword in the relevant field list appears in
        the corresponding part of the request/response.

    match_mode = "keyword_list":
        A branch is preserved when the accumulated text from root to the node
        collectively contains ALL keywords in `keyword_list`.

    combinations:
        Each combination is evaluated branch-by-branch across the filtered
        tree.  All keywords in a combination must appear in their respective
        fields somewhere along the branch path.
    """

    version: str = "1.0"
    name: str = "Custom Filter"
    description: Optional[str] = None

    # Per-field keyword lists (used when match_mode == "any_field").
    # Each entry is either a plain string or {"keyword": str, "weight": int}.
    url_keywords: List[Any] = Field(default_factory=list)
    req_header_keywords: List[Any] = Field(default_factory=list)
    res_header_keywords: List[Any] = Field(default_factory=list)
    req_body_keywords: List[Any] = Field(default_factory=list)
    res_body_keywords: List[Any] = Field(default_factory=list)

    # AND-list (used when match_mode == "keyword_list")
    keyword_list: List[Any] = Field(default_factory=list)

    match_mode: Literal["any_field", "keyword_list"] = "any_field"

    # Combinations — always evaluated regardless of match_mode
    combinations: List[CombinationEntry] = Field(default_factory=list)


class CustomFilterRequest(BaseModel):
    """Payload accepted by POST /api/filter-custom."""
    root_url: str = ""
    har_files: List[str] = []
    tree: Optional[Dict[str, Any]] = None
    orphan_nodes: List[Dict[str, Any]] = []
    total_entries_filtered: int = 0
    summary: Dict[str, Any] = {}
    config: CustomFilterConfig