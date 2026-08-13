from app.connectors.read.woocommerce import _normalize_product, _normalize_variation


def test_woocommerce_product_normalization_captures_ordered_canonical_media():
    product = _normalize_product(
        {
            "id": 101,
            "type": "simple",
            "name": "Media product",
            "images": [
                {"id": 1, "src": "https://cdn.example.test/primary.jpg?consumer_key=secret"},
                {"src": "not-a-url"},
                {"id": 3, "src": "https://cdn.example.test/alternate.jpg#private"},
            ],
        }
    )

    assert product is not None
    assert product["primary_image_url"] == "https://cdn.example.test/primary.jpg"
    assert product["media"] == [
        {
            "type": "image",
            "url": "https://cdn.example.test/primary.jpg",
            "position": 0,
            "source": "woocommerce",
        },
        {
            "type": "image",
            "url": "https://cdn.example.test/alternate.jpg",
            "position": 2,
            "source": "woocommerce",
        },
    ]
    assert "images" not in product
    assert "consumer_key" not in repr(product)


def test_woocommerce_product_without_images_remains_valid():
    product = _normalize_product({"id": 102, "type": "simple", "images": None})

    assert product is not None
    assert product["media"] == []
    assert product["primary_image_url"] is None


def test_woocommerce_variation_media_is_normalized_without_raw_provider_image():
    variation = _normalize_variation(
        {
            "id": 201,
            "image": {"src": "https://cdn.example.test/variation.jpg?token=secret"},
        },
        {"product_id": "200", "name": "Parent", "categories": []},
    )

    assert variation is not None
    assert variation["media"][0]["url"] == "https://cdn.example.test/variation.jpg"
    assert variation["primary_image_url"] == "https://cdn.example.test/variation.jpg"
    assert "image" not in variation
    assert "token" not in repr(variation)
