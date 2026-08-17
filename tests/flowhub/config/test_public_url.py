from app.flowhub.config.public_url import canonical_public_url, public_webhook_url


def test_public_webhook_url_uses_canonical_base_and_encodes_channel_id():
    assert public_webhook_url(
        "woocommerce",
        "woocommerce:primary",
        public_url="https://flowhub.softpple.business/",
    ) == "https://flowhub.softpple.business/api/v2/webhooks/woocommerce/woocommerce%3Aprimary"


def test_public_webhook_url_does_not_use_internal_server_when_public_url_is_set():
    assert public_webhook_url(
        "woocommerce",
        "woocommerce:primary",
        public_url="https://flowhub.softpple.business",
    ) != "http://192.168.10.80:8085/api/v2/webhooks/woocommerce/woocommerce%3Aprimary"


def test_canonical_public_url_normalizes_trailing_slash_and_rejects_non_url():
    assert canonical_public_url("https://flowhub.softpple.business///") == "https://flowhub.softpple.business"
    assert canonical_public_url("flowhub.softpple.business") is None
