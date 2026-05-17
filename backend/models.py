from __future__ import annotations
from typing import Any, Dict, List, Literal, Optional
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


class ResponseDetail(BaseModel):
    status: int
    status_text: str
    headers: List[HeaderEntry] = []
    cookies: List[CookieEntry] = []
    body: Optional[str] = None
    body_mime_type: Optional[str] = None
    body_parsed: Optional[Any] = None
    redirect_url: Optional[str] = None


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

class CustomFilterConfig(BaseModel):
    """
    Configuration for the custom keyword filter.

    match_mode = "any_field":
        A node matches if ANY keyword in the relevant field list appears in
        the corresponding part of the request/response.  Branches that contain
        at least one match are preserved in full below the match point.

    match_mode = "keyword_list":
        A branch is preserved when the accumulated text from the tree root down
        to (and including) a node collectively contains ALL keywords in
        `keyword_list`.  Individual field filters are ignored in this mode.
    """

    version: str = "1.0"
    name: str = "Custom Filter"
    description: Optional[str] = None

    # Per-field keyword lists (used when match_mode == "any_field")
    url_keywords: List[str] = Field(default_factory=list)
    req_header_keywords: List[str] = Field(default_factory=list)
    res_header_keywords: List[str] = Field(default_factory=list)
    req_body_keywords: List[str] = Field(default_factory=list)
    res_body_keywords: List[str] = Field(default_factory=list)

    # AND-list (used when match_mode == "keyword_list")
    keyword_list: List[str] = Field(default_factory=list)

    match_mode: Literal["any_field", "keyword_list"] = "any_field"


class CustomFilterRequest(BaseModel):
    """Payload accepted by POST /api/filter-custom."""
    root_url: str = ""
    har_files: List[str] = []
    tree: Optional[Dict[str, Any]] = None
    orphan_nodes: List[Dict[str, Any]] = []
    total_entries_filtered: int = 0
    summary: Dict[str, Any] = {}
    config: CustomFilterConfig
