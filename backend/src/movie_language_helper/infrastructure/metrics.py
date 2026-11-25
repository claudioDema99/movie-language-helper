"""Content-free in-process metrics in Prometheus text format."""

from __future__ import annotations

import re
from collections import Counter
from threading import Lock

SESSION_PATH = re.compile(r"/api/v1/transcript-sessions/[^/]+")
MOVIE_PATH = re.compile(r"/api/v1/movies/[^/]+")


def route_label(path: str) -> str:
    """Remove opaque identifiers before using a path as a metric label."""
    path = SESSION_PATH.sub("/api/v1/transcript-sessions/{id}", path)
    return MOVIE_PATH.sub("/api/v1/movies/{id}", path)


class MetricsRegistry:
    """Small process-local registry; no content or unbounded labels."""

    def __init__(self) -> None:
        self._lock = Lock()
        self._http: Counter[tuple[str, str, str]] = Counter()
        self._http_duration_ms = 0
        self._http_duration_count = 0
        self._errors: Counter[str] = Counter()
        self._analysis_count = 0
        self._analysis_latency_ms = 0
        self._input_tokens = 0
        self._output_tokens = 0

    def observe_http(
        self, method: str, path: str, status_code: int, duration_ms: int
    ) -> None:
        with self._lock:
            self._http[(method, route_label(path), f"{status_code // 100}xx")] += 1
            self._http_duration_ms += duration_ms
            self._http_duration_count += 1

    def observe_error(self, code: str) -> None:
        with self._lock:
            self._errors[code] += 1

    def observe_analysis(
        self,
        *,
        latency_ms: int,
        input_tokens: int | None,
        output_tokens: int | None,
    ) -> None:
        with self._lock:
            self._analysis_count += 1
            self._analysis_latency_ms += latency_ms
            self._input_tokens += input_tokens or 0
            self._output_tokens += output_tokens or 0

    def render(self) -> str:
        with self._lock:
            lines = [
                "# HELP mlh_http_requests_total HTTP requests by bounded route.",
                "# TYPE mlh_http_requests_total counter",
            ]
            for (method, route, status_class), value in sorted(self._http.items()):
                lines.append(
                    "mlh_http_requests_total"
                    f'{{method="{method}",route="{route}",status="{status_class}"}} '
                    f"{value}"
                )
            lines.extend(
                (
                    "# TYPE mlh_http_duration_milliseconds_sum counter",
                    f"mlh_http_duration_milliseconds_sum {self._http_duration_ms}",
                    "# TYPE mlh_http_duration_milliseconds_count counter",
                    f"mlh_http_duration_milliseconds_count {self._http_duration_count}",
                    "# TYPE mlh_analysis_requests_total counter",
                    f"mlh_analysis_requests_total {self._analysis_count}",
                    "# TYPE mlh_analysis_latency_milliseconds_sum counter",
                    "mlh_analysis_latency_milliseconds_sum "
                    f"{self._analysis_latency_ms}",
                    "# TYPE mlh_analyzer_input_tokens_total counter",
                    f"mlh_analyzer_input_tokens_total {self._input_tokens}",
                    "# TYPE mlh_analyzer_output_tokens_total counter",
                    f"mlh_analyzer_output_tokens_total {self._output_tokens}",
                    "# TYPE mlh_errors_total counter",
                )
            )
            for code, value in sorted(self._errors.items()):
                lines.append(f'mlh_errors_total{{code="{code}"}} {value}')
            return "\n".join(lines) + "\n"
