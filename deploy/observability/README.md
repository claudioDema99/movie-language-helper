# Observability templates

`alerts.yml` contains Prometheus-compatible starter alerts and
`grafana-dashboard.json` is an importable dashboard using a datasource named
`Prometheus`. They use only metrics currently emitted by the backend plus
Prometheus's standard `up` metric.

Configure Prometheus to scrape `http://backend:8000/metrics` on the private
Compose network and authenticate with `bearer_token_file` pointing to the same
read-only `private_access_token` secret. Do not expose `/metrics` publicly just
to make scraping convenient. Configure notification receivers and tune every
threshold against staging traffic before treating these templates as paging
policy.
