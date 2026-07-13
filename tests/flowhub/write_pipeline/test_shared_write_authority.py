"""Architecture guards for the single active external-write authority."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
APPROVED_PROVIDER_BOUNDARIES = {
    Path("app/flowhub/write_pipeline/service.py"),
    Path("app/flowhub/unified_workspace/connectors.py"),
}


def test_no_active_service_dispatches_outside_shared_write_pipeline() -> None:
    violations: list[str] = []
    for path in (ROOT / "app/flowhub").rglob("*.py"):
        relative = path.relative_to(ROOT)
        if relative in APPROVED_PROVIDER_BOUNDARIES:
            continue
        source = path.read_text(encoding="utf-8")
        for forbidden in (".execute_item(", ".update_products("):
            if forbidden in source:
                violations.append(f"{relative.as_posix()}: {forbidden}")
    assert violations == []


def test_product_pricing_is_a_compatibility_facade_over_write_pipeline() -> None:
    source = (ROOT / "app/flowhub/product_pricing/service.py").read_text(
        encoding="utf-8"
    )
    assert "WritePipelineService(self.db).execute_product_pricing_item" in source
    assert "WooCommercePriceWriteAdapter" not in source
    assert ".update_products(" not in source
    assert "_update_cache_after_success" not in source


def test_all_active_workflows_use_the_provider_neutral_attempt_model() -> None:
    pipeline = (ROOT / "app/flowhub/write_pipeline/service.py").read_text(
        encoding="utf-8"
    )
    assert 'source_workflow="unified_workspace"' in pipeline
    assert 'source_workflow="product_pricing"' in pipeline
    assert "ProviderWriteAttempt(" in pipeline
    assert "ProviderWriteAttemptEvent(" in pipeline
    assert "ApplyAttempt(" not in pipeline


def test_legacy_execute_is_only_a_compatibility_facade() -> None:
    """The legacy endpoint must not contain a second provider state machine."""
    pipeline = (ROOT / "app/flowhub/write_pipeline/service.py").read_text(
        encoding="utf-8"
    )
    execute_start = pipeline.index("    async def execute(")
    execute_end = pipeline.index("    def _legacy_listing_id", execute_start)
    legacy_body = pipeline[execute_start:execute_end]
    assert "execute_workspace(" in legacy_body
    assert ".execute_item(" not in legacy_body
    assert "ProviderWriteAttempt(" not in legacy_body
    assert "ProviderWriteAttemptEvent(" not in legacy_body


def test_legacy_adapter_payload_has_stable_attempt_identity() -> None:
    pipeline = (ROOT / "app/flowhub/write_pipeline/service.py").read_text(
        encoding="utf-8"
    )
    helper_start = pipeline.index("    def _legacy_batch_command(")
    helper_end = pipeline.index("    async def execute_workspace(", helper_start)
    helper = pipeline[helper_start:helper_end]
    assert "payload_hash" in helper
    assert "idempotency_key" in helper
    assert 'source_workflow="legacy_write_pipeline"' in helper


def test_production_entrypoint_excludes_legacy_compatibility_writes() -> None:
    dockerfile = (ROOT / "Dockerfile").read_text(encoding="utf-8")
    assert "app.flowhub.app:app" in dockerfile
    assert "app.main:app" not in dockerfile
