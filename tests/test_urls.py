from bot.urls import public_url


def test_replaces_legacy_apbook_host_and_preserves_url_parts():
    assert public_url(
        "http://apbook.yanao.int/books/gis-esku/page/help?mode=full#section"
    ) == "https://apbook.yanao.ru/books/gis-esku/page/help?mode=full#section"


def test_keeps_other_hosts_unchanged():
    url = "https://instructions.yanao.ru/books/rsed/page/help"
    assert public_url(url) == url
