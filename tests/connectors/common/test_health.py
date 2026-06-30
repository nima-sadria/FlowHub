from app.connectors.common.health import HealthResult, HealthStatus


def test_health_status_values():
    assert HealthStatus.HEALTHY.value == "healthy"
    assert HealthStatus.DEGRADED.value == "degraded"
    assert HealthStatus.UNHEALTHY.value == "unhealthy"


def test_health_result_healthy():
    r = HealthResult(status=HealthStatus.HEALTHY, latency_ms=12.5)
    assert r.status == HealthStatus.HEALTHY
    assert r.latency_ms == 12.5
    assert r.detail is None


def test_health_result_unhealthy_with_detail():
    r = HealthResult(status=HealthStatus.UNHEALTHY, detail="connection refused")
    assert r.status == HealthStatus.UNHEALTHY
    assert r.detail == "connection refused"
    assert r.latency_ms is None


def test_health_result_degraded():
    r = HealthResult(status=HealthStatus.DEGRADED, latency_ms=950.0, detail="slow response")
    assert r.status == HealthStatus.DEGRADED
