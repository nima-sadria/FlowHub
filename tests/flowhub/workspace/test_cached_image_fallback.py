from types import SimpleNamespace

from app.flowhub.workspace.price_workflow import _resolved_image_url


def _product(*, images, product_type="simple", parent_id=None):
    return SimpleNamespace(images=images, product_type=product_type, parent_id=parent_id)


def test_variation_image_is_preferred_over_parent_image():
    variation = _product(
        images=[{"src": "https://cdn.example/variation.jpg"}],
        product_type="variation",
        parent_id="100",
    )
    parent = _product(images=[{"src": "https://cdn.example/parent.jpg"}])

    assert _resolved_image_url(variation, {"100": parent}) == "https://cdn.example/variation.jpg"


def test_variation_uses_cached_parent_image_without_provider_read():
    variation = _product(images=[], product_type="variation", parent_id="100")
    parent = _product(images=[{"src": "https://cdn.example/parent.jpg"}])

    assert _resolved_image_url(variation, {"100": parent}) == "https://cdn.example/parent.jpg"


def test_missing_cached_images_return_placeholder_signal():
    variation = _product(images=[], product_type="variation", parent_id="100")

    assert _resolved_image_url(variation, {}) is None
