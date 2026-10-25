# AI Disclosure — DA3408 A4: Application Monitoring with Prometheus & Grafana

**Student:** DA24B037
**Assignment:** A4 — Application Monitoring: Observability with Prometheus & Grafana
**AI Tool Used:** Claude (Anthropic)

This document discloses AI assistance used in this assignment, per the course's Code of Conduct on Fair Use of AI, including the "Black Box" Metric Rule requiring attribution for AI-generated PromQL.

## What AI Was Used For

### 1. Application Code (`app.py`)
The Streamlit image captioning app and its `prometheus_client` instrumentation (Counters, Gauges, Histogram, Summary, custom labels) were drafted with AI assistance. All metric definitions, their semantics, and what they measure were manually reviewed and verified by running the app and confirming real values via `curl http://localhost:8000/metrics` and PromQL queries in Prometheus before being considered correct.

### 2. Debugging
AI helped diagnose a `DuplicateTimeseries` crash caused by Streamlit re-running the entire script on every UI interaction, which re-executed module-level Prometheus metric constructors. The fix (wrapping metric creation in an idempotent `_get_or_create` helper that checks the registry before creating a new collector) was AI-suggested and manually verified by confirming the app no longer crashed across repeated reruns and that metric values accumulated correctly (not reset) across interactions.

### 3. Infrastructure Config (`prometheus.yml`)
The Prometheus scrape configuration, including the two scrape jobs for the app (`localhost:8000`) and node_exporter (`localhost:9100`), was AI-drafted and manually verified via the Prometheus `/targets` page, confirming both show state `UP`.

### 4. PromQL Queries (Black Box Metric Rule — Attribution)
The following PromQL queries used in `dashboard_export.json` were AI-generated. Per the Black Box Metric Rule, each is listed here with the prompt/intent behind it, and each was **manually calculated/verified** against raw metric values from `/metrics` and cross-checked in Prometheus's own query UI before being trusted:

| Panel | PromQL | Prompt / Intent | Manual Verification |
|---|---|---|---|
| Application Health | `up{job="captioning_app"}` | "Show whether the app's /metrics endpoint is reachable" | Confirmed value flips to 0 when the app process is stopped, 1 when running |
| Throughput | `sum by (mode) (rate(captioning_images_processed_total[1m]))` | "Rate of images processed per second, split by single/bulk" | Manually computed rate = (counter delta) / (time delta) between two `curl` snapshots and compared to the graphed value |
| Latency p50/p95 | `histogram_quantile(0.50/0.95, sum by (le, mode) (rate(captioning_inference_seconds_bucket[5m])))` | "Show median and 95th-percentile per-image inference latency" | Cross-checked against the raw `_bucket` counts returned by `/metrics` for a known small batch |
| Error Rate | `sum by (mode) (rate(captioning_errors_total[1m]))` | "Rate of failed captioning attempts" | Confirmed panel shows 0/"No data" correctly, since no errors were triggered during testing |
| System CPU % | `100 - (avg by (instance) (rate(node_cpu_seconds_total{mode="idle"}[1m])) * 100)` | "Standard node_exporter idle-time-based CPU utilization formula" | Compared against `top`/`free -h` output on the host during a bulk upload, values were consistent |
| System Memory % | `(1 - (node_memory_MemAvailable_bytes / node_memory_MemTotal_bytes)) * 100` | "Standard node_exporter available-memory-based utilization formula" | Compared against `free -h` output, values were consistent |
| Caption Length (avg) | `sum by (mode) (rate(captioning_caption_length_chars_sum[5m])) / sum by (mode) (rate(captioning_caption_length_chars_count[5m]))` | "Average caption length over time from the Summary metric" | Manually divided the raw `_sum` and `_count` values from `/metrics` for a known set of captions and matched the panel value |
| Last Bulk Batch Size | `captioning_last_bulk_batch_size` | "Show the size of the most recent ZIP batch" (direct gauge, no query logic) | Trivial — gauge value directly set by the app, confirmed against the ZIP's actual file count |

### 5. Dashboard JSON Structure
The Grafana dashboard JSON (panel layout, field configs, color palette choices) was AI-drafted to satisfy the Seven Commandments (color-blind-safe palette using blue/orange/purple rather than red/green, named axes with explicit units, legends, titles/subtitles via panel description fields). This was pushed via the Grafana HTTP API and manually reviewed in the browser to confirm each panel renders correctly and the described visual requirements are met.

## What Was NOT AI-Generated

- **All metric values and dashboard data** are real, captured from an actual running instance of the app, Prometheus, and node_exporter — none are synthetic or fabricated.
- **Cluster/service setup** (starting node_exporter, Prometheus, the Streamlit app, and Grafana) was performed manually by the student via terminal commands.
- **Manual verification** of every AI-generated PromQL query, as detailed in the table above, was performed by the student before accepting the query as correct.

## Known Limitation

Per the assignment's requirements, a ~1-minute screen recording of the dashboard at 5-second refresh was **not completed** and is not included in this submission. This is noted here as a disclosed gap rather than omitted silently.
