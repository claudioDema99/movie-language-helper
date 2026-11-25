"""Private-profile controls and content-free metrics."""

from movie_language_helper.infrastructure.metrics import MetricsRegistry, route_label
from movie_language_helper.infrastructure.security import (
    FixedWindowRateLimiter,
    bearer_token,
    client_key,
    token_matches,
)


def test_fixed_window_rate_limiter_resets_and_reports_retry() -> None:
    limiter = FixedWindowRateLimiter(2, 10)
    assert limiter.check("client", 11) is None
    assert limiter.check("client", 12) is None
    assert limiter.check("client", 13) == 7
    assert limiter.check("client", 20) is None


def test_authentication_helpers_are_strict_and_hash_client_identity() -> None:
    assert bearer_token(None) is None
    assert bearer_token("Basic value") is None
    assert bearer_token("Bearer ") is None
    assert bearer_token("Bearer secret") == "secret"
    assert token_matches("secret", "secret") is True
    assert token_matches(None, "secret") is False
    assert client_key("1.2.3.4, 5.6.7.8", "peer") == client_key("1.2.3.4", "other")
    assert client_key(None, "peer") != client_key(None, "other")


def test_metrics_remove_ids_and_render_only_bounded_labels() -> None:
    metrics = MetricsRegistry()
    metrics.observe_http("GET", "/api/v1/movies/42/subtitles", 200, 12)
    metrics.observe_http("GET", "/api/v1/transcript-sessions/secret/preview", 404, 3)
    metrics.observe_error("session_not_found")
    metrics.observe_analysis(latency_ms=9, input_tokens=10, output_tokens=None)
    text = metrics.render()
    assert route_label("/api/v1/movies/42/subtitles") == (
        "/api/v1/movies/{id}/subtitles"
    )
    assert "secret" not in text
    assert 'status="2xx"' in text
    assert 'status="4xx"' in text
    assert 'code="session_not_found"' in text
    assert "mlh_analyzer_input_tokens_total 10" in text
    assert "mlh_analyzer_output_tokens_total 0" in text
