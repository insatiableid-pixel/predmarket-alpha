# Monitoring and Deployment Observability

## Health and Status Endpoints

- **Prometheus /metrics**: `GET /metrics` exposes Prometheus-format metrics
  (request latency, error counts, active connections).
- **FastAPI health**: `GET /health` returns service liveness.
- **Dashboard**: `GET /` (port 8050) serves the Dash research dashboard.

## Error Tracking

- **Sentry**: If `SENTRY_DSN` is set, errors are sent to Sentry with
  breadcrumbs, tags, and full stack traces. Configure via `.env`:
  ```
  SENTRY_DSN=https://<key>@sentry.io/<project>
  SENTRY_ENVIRONMENT=research
  ```
- **Local fallback**: Without Sentry, errors are logged with structured
  context (error ID, breadcrumbs, tags) via `predmarket.observability`.

## Alerting

- **Slack webhook**: If `ALERT_SLACK_WEBHOOK` is set, critical errors are
  posted to Slack with error ID, type, message, and context.
- **GitHub issue automation**: The `error-triage.yml` workflow checks for
  CI failures daily and creates a labeled GitHub issue automatically.

## Metrics Collection

- **prometheus-client**: The `/metrics` endpoint exposes:
  - HTTP request latency histograms
  - Error counters
  - Active connection gauges
  - Custom research-desk metrics

## Deployment Impact

When checking the impact of a deployment:
1. Check CI status: `gh run list --limit 5`
2. Review Sentry for new errors (if configured)
3. Check `/metrics` for latency/error spikes
4. Review the Dash dashboard for research-desk health
5. Check the error-triage GitHub issues for any auto-created tickets

## Request Tracing

- Every HTTP request gets an `X-Request-ID` header (via
  `predmarket.request_context.RequestIdMiddleware`). The ID is logged
  with the request completion and can be used to correlate logs across
  the system.
