from __future__ import annotations

from urllib.parse import urlsplit, urlunsplit


LEGACY_APBOOK_HOSTS = frozenset({"apbook.yanao.int"})
PUBLIC_APBOOK_HOST = "apbook.yanao.ru"


def public_url(url: str) -> str:
    """Replace the legacy internal APBook host with its public HTTPS address."""
    try:
        parts = urlsplit(url)
    except ValueError:
        return url
    if (parts.hostname or "").lower() not in LEGACY_APBOOK_HOSTS:
        return url
    return urlunsplit(("https", PUBLIC_APBOOK_HOST, parts.path, parts.query, parts.fragment))
