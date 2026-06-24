"""识别增强审计摘要工具。"""
import hashlib
import re

from ..shared.log import truncate_log_value


_URL_RE = re.compile(r"(?:https?|ftp)://\S+|magnet:\?\S+", re.IGNORECASE)
_AUTH_SCHEME_RE = re.compile(
    r"(?i)\b(?:authorization|auth)\s*[:=]\s*(?:bearer|basic|digest|token)\s+[^\s&;,|]+"
)
_SECRET_RE = re.compile(
    r"(?i)\b(token|passkey|apikey|api_key|authorization|auth|password|passwd|pwd|sid|session|cookie)"
    r"\s*[:=]\s*[^&\s]+"
)
_COOKIE_HEADER_RE = re.compile(r"(?i)\bcookie\s*:\s*[^&\s]+")
_LOCAL_PATH_RE = re.compile(r"(?:/[^\s|；;，,]+){2,}")


def candidate_fingerprint(torrent_info) -> str:
    """生成稳定候选指纹；输入可含敏感 URL，但输出只暴露不可逆短摘要。"""
    raw = "\n".join([
        str(getattr(torrent_info, "enclosure", "") or ""),
        str(getattr(torrent_info, "page_url", "") or ""),
        str(getattr(torrent_info, "site_name", "") or getattr(torrent_info, "site", "") or ""),
        str(getattr(torrent_info, "title", "") or ""),
    ])
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:16]


def redact_sensitive_text(value) -> str:
    """脱敏审计文本中的链接和常见凭据字段，避免日志暴露站点令牌。"""
    text = str(value or "")
    text = _URL_RE.sub("[redacted-url]", text)
    text = _AUTH_SCHEME_RE.sub("[redacted-secret]", text)
    text = _COOKIE_HEADER_RE.sub("[redacted-secret]", text)
    text = _SECRET_RE.sub("[redacted-secret]", text)
    return _LOCAL_PATH_RE.sub("[redacted-path]", text)


def sanitize_candidate_summary(torrent_info, max_length: int = 220) -> str:
    """候选审计摘要：只保留站点、短指纹和可展示文本，避免泄漏下载链接参数。"""
    site = getattr(torrent_info, "site_name", None) or getattr(torrent_info, "site", None) or "-"
    title = truncate_log_value(redact_sensitive_text(getattr(torrent_info, "title", "") or ""), 120)
    desc = truncate_log_value(redact_sensitive_text(getattr(torrent_info, "description", "") or ""), 80)
    fp = candidate_fingerprint(torrent_info)
    return truncate_log_value(f"{site} #{fp} {title} {desc}", max_length)
