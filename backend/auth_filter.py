"""
auth_filter.py
Filters a RequestNode tree to only auth-relevant nodes.
"""
from __future__ import annotations
import re
from typing import Optional
from models import RequestNode

AUTH_DOMAIN_FRAGMENTS = [
    "cognito-idp.", "auth0.com", "okta.com", "onelogin.com",
    "pingone.com", "pingidentity.com", "keycloak",
    "accounts.google.com", "oauth2.googleapis.com",
    "openidconnect.googleapis.com", "identitytoolkit.googleapis.com",
    "securetoken.googleapis.com", "login.microsoftonline.com",
    "login.live.com", "login.windows.net", "appleid.apple.com",
    "api.twitter.com", "accounts.spotify.com", "id.twitch.tv",
    "zoom.us/oauth", "gitlab.com/oauth", "login.salesforce.com",
    "sso.amazonaws.com", "login.", "sso.", "idp.", ".auth.",
    "oauth.", "openid.", "saml.", "adfs.", "signin.", "identity.",
]

NOISE_HOSTS = {
    "www.google-analytics.com","analytics.google.com","www.googletagmanager.com",
    "region1.google-analytics.com","stats.g.doubleclick.net","bat.bing.com",
    "cdn.segment.com","api.segment.io","heapanalytics.com","fullstory.com",
    "logrocket.com","sentry.io","ingest.sentry.io","datadoghq.com",
    "nr-data.net","newrelic.com","hotjar.com","clarity.ms","c.clarity.ms",
    "cdn.cookielaw.org","www.gstatic.com","fonts.googleapis.com",
    "fonts.gstatic.com","use.fontawesome.com","kit.fontawesome.com",
    "cdn.jsdelivr.net","unpkg.com","cdnjs.cloudflare.com","www.recaptcha.net",
}

AUTH_PATH_RE = re.compile(
    r'/(oauth[2]?|oidc|authorize|authorise|token|access[_\-]token'
    r'|refresh[_\-]?token|revoke|introspect|userinfo|jwks(\.json)?'
    r'|\.well-known/(openid-configuration|oauth-authorization-server|jwks)'
    r'|login|logout|sign[_\-]?in|sign[_\-]?out|signout|signin'
    r'|session[s]?|auth|authenticate|authentication'
    r'|callback|redirect|authorized|saml[2]?sso|saml[2]?'
    r'|sso|password|forgot[_\-]?password|reset[_\-]?password|change[_\-]?password'
    r'|credentials|mfa|totp|otp|two[_\-]?factor'
    r'|verify|verification|register|confirm|invite'
    r'|api[_\-]?key[s]?|AWSCognitoIdentityProviderService'
    r'|challenge|permission[s]?|role[s]?|grant)(/|$|\?)',
    re.IGNORECASE,
)

AUTH_QUERY_RE = re.compile(
    r'[?&](code|state|nonce|id_token|access_token|token|grant_type'
    r'|response_type|client_id|redirect_uri|scope|code_challenge'
    r'|code_verifier|error|error_description'
    r'|SAMLRequest|SAMLResponse|RelayState)=',
    re.IGNORECASE,
)

AUTH_REQ_HEADERS = {
    "authorization","x-access-token","x-auth-token","x-api-key",
    "x-session-token","x-id-token","x-refresh-token","x-csrf-token",
    "x-xsrf-token","x-amz-security-token","x-amz-target",
    "www-authenticate","proxy-authorization",
}

AUTH_RESP_HEADERS = {"www-authenticate","x-auth-token","x-access-token","x-id-token"}

AUTH_COOKIE_RE = re.compile(
    r'(session|sess|auth|token|jwt|csrf|xsrf|access|refresh|id_token'
    r'|cognito|amplify|oidc|oauth|sso|login|logged|identity|credentials'
    r'|remember[_\-]?me|keep[_\-]?login|bearer|api[_\-]?key)',
    re.IGNORECASE,
)

AUTH_BODY_RE = re.compile(
    r'["\s,{](grant_type|client_id|client_secret|client_assertion'
    r'|code|state|nonce|scope|access_token|id_token|refresh_token'
    r'|token_type|expires_in|SRP_A|SRP_B|SECRET_HASH|USERNAME|PASSWORD'
    r'|NEW_PASSWORD|AuthFlow|AuthParameters|ChallengeName|ChallengeResponses'
    r'|assertion|saml_response|id_token_hint|post_logout_redirect_uri'
    r'|code_verifier|code_challenge|redirect_uri|response_type'
    r'|cognitoAccessToken|cognitoRefreshToken)["\s:,}]',
    re.IGNORECASE,
)

COGNITO_TARGETS = {
    "AWSCognitoIdentityProviderService.InitiateAuth",
    "AWSCognitoIdentityProviderService.RespondToAuthChallenge",
    "AWSCognitoIdentityProviderService.GetUser",
    "AWSCognitoIdentityProviderService.RefreshTokens",
    "AWSCognitoIdentityProviderService.RevokeToken",
    "AWSCognitoIdentityProviderService.SignUp",
    "AWSCognitoIdentityProviderService.ConfirmSignUp",
    "AWSCognitoIdentityProviderService.ForgotPassword",
    "AWSCognitoIdentityProviderService.ConfirmForgotPassword",
    "AWSCognitoIdentityProviderService.ChangePassword",
    "AWSCognitoIdentityProviderService.GlobalSignOut",
}

STATIC_EXTS = {
    ".css",".js",".map",".png",".jpg",".jpeg",".gif",".svg",".webp",
    ".avif",".ico",".woff",".woff2",".ttf",".otf",".eot",
    ".mp4",".mp3",".webm",".ogg",".wav",".pdf",".zip",".gz",
}


def _is_auth_node(node: RequestNode) -> bool:
    url    = node.url or ""
    domain = (node.domain or "").lower().split(":")[0]
    path   = (node.path or "").lower()

    if domain in NOISE_HOSTS:
        return False

    path_no_qs = path.split("?")[0]
    ext = "." + path_no_qs.rsplit(".", 1)[-1] if "." in path_no_qs.split("/")[-1] else ""
    if ext in STATIC_EXTS:
        return False

    for frag in AUTH_DOMAIN_FRAGMENTS:
        if frag in domain:
            return True

    if AUTH_PATH_RE.search(url):
        return True

    if AUTH_QUERY_RE.search(url):
        return True

    req_hdr_names = {h.name.lower() for h in node.request.headers}
    if req_hdr_names & AUTH_REQ_HEADERS:
        return True

    for h in node.request.headers:
        if h.name.lower() == "x-amz-target" and h.value in COGNITO_TARGETS:
            return True

    for c in node.request.cookies:
        if AUTH_COOKIE_RE.search(c.name):
            return True

    for h in node.response.headers:
        if h.name.lower() == "set-cookie":
            cookie_name = h.value.split("=")[0].strip()
            if AUTH_COOKIE_RE.search(cookie_name):
                return True
        if h.name.lower() in AUTH_RESP_HEADERS:
            return True

    req_body = node.request.body or ""
    if req_body and AUTH_BODY_RE.search(req_body):
        return True
    if isinstance(node.request.body_parsed, dict):
        if AUTH_BODY_RE.search(" ".join(node.request.body_parsed.keys())):
            return True

    resp_body = node.response.body or ""
    if resp_body and AUTH_BODY_RE.search(resp_body):
        return True
    if isinstance(node.response.body_parsed, dict):
        if AUTH_BODY_RE.search(" ".join(node.response.body_parsed.keys())):
            return True

    redir = node.response.redirect_url or ""
    if redir:
        for frag in AUTH_DOMAIN_FRAGMENTS:
            if frag in redir.lower():
                return True
        if AUTH_PATH_RE.search(redir) or AUTH_QUERY_RE.search(redir):
            return True

    if node.status in (401, 403):
        return True

    return False


def filter_auth_nodes(node: RequestNode) -> Optional[RequestNode]:
    filtered_children = []
    for child in node.children:
        r = filter_auth_nodes(child)
        if r is not None:
            filtered_children.append(r)

    if not _is_auth_node(node) and not filtered_children:
        return None

    copy = node.model_copy(deep=False)
    copy.children = filtered_children
    return copy


def _count(n: Optional[RequestNode]) -> int:
    if n is None:
        return 0
    return 1 + sum(_count(c) for c in n.children)


def filter_auth_tree(tree_dict: dict) -> dict:
    root = RequestNode.model_validate(tree_dict["tree"])
    filtered_root = filter_auth_nodes(root)

    filtered_orphans = []
    for o in tree_dict.get("orphan_nodes", []):
        on = RequestNode.model_validate(o)
        if _is_auth_node(on):
            filtered_orphans.append(on)

    return {
        "root_url": tree_dict.get("root_url", ""),
        "har_files": tree_dict.get("har_files", []),
        "total_auth_nodes": _count(filtered_root) + len(filtered_orphans),
        "original_total": tree_dict.get("total_entries_filtered", 0),
        "tree": filtered_root.model_dump(exclude_none=True) if filtered_root else None,
        "orphan_nodes": [o.model_dump(exclude_none=True) for o in filtered_orphans],
    }