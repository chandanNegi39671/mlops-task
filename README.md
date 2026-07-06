# MLOps Batch Pipeline

A minimal, production-quality MLOps batch job that ingests OHLCV market data,
computes a rolling-mean signal, and emits structured metrics — fully Dockerized
and deterministic.

---

## Project Overview

| Step | What happens |
|------|-------------|
| Config load | Reads `config.yaml`, validates required fields |
| Data load | Reads `data.csv`, validates shape and `close` column |
| Rolling mean | `close.rolling(window).mean()` — first `window-1` NaN rows dropped |
| Signal | `1` if `close > rolling_mean`, else `0` |
| Metrics | JSON written to `--output`; final JSON also printed to stdout |
| Logging | Timestamped INFO log written to `--log-file` |

---

## Requirements

- Python 3.9+
- pip packages: `pandas`, `numpy`, `PyYAML`
- Docker (for containerised run)

---

## Local Setup

```bash
pip install -r requirements.txt
```

---

## Local Execution

```bash
python run.py \
  --input    data.csv \
  --config   config.yaml \
  --output   metrics.json \
  --log-file run.log
```

After a successful run you will see:
- `metrics.json` — structured output
- `run.log` — timestamped execution log

---

## Docker Build

```bash
docker build -t mlops-task .
```

---

## Docker Run

```bash
docker run --rm mlops-task
```

The container:
- Runs the pipeline with `data.csv` and `config.yaml` baked in
- Prints the final `metrics.json` to stdout
- Exits `0` on success, non-zero on failure

To extract output files from the container:

```bash
# Run with a named container, copy files out, then remove
docker run --name mlops-run mlops-task
docker cp mlops-run:/app/metrics.json ./metrics.json
docker cp mlops-run:/app/run.log ./run.log
docker rm mlops-run
```

---

## Project Structure

```
mlops-task/
├── run.py           # Pipeline: config → data → signal → metrics
├── config.yaml      # Runtime config (seed, window, version)
├── data.csv         # 10,000-row OHLCV dataset
├── requirements.txt # pandas, numpy, PyYAML
├── Dockerfile       # python:3.9-slim image
├── metrics.json     # Sample success output
├── run.log          # Sample execution log
└── README.md        # This file
```

---

## config.yaml

```yaml
seed: 42
window: 5
version: "v1"
```

| Field | Type | Description |
|-------|------|-------------|
| `seed` | int | NumPy random seed for reproducibility |
| `window` | int | Rolling mean window size (must be ≥ 1) |
| `version` | str | Pipeline version tag, written to metrics |

---

## Example metrics.json (success)

```json
{
  "version": "v1",
  "rows_processed": 9996,
  "metric": "signal_rate",
  "value": 0.4991,
  "latency_ms": 20,
  "seed": 42,
  "status": "success"
}
```

> **Note on `rows_processed`:** with `window=5`, the first 4 rows have no full
> rolling window and are excluded, giving 9,996 valid rows from 10,000 input rows.

---

## Error Handling

All validation errors write an error payload to `--output` before exiting non-zero:

```json
{
  "version": "v1",
  "status": "error",
  "error_message": "Required column 'close' not found. ..."
}
```

Handled error cases:

| Case | Behaviour |
|------|-----------|
| Config file missing | `FileNotFoundError`, error metrics written |
| Invalid YAML | `ValueError`, error metrics written |
| Missing config fields (`seed`/`window`/`version`) | `KeyError`, error metrics written |
| `window < 1` | `ValueError`, error metrics written |
| Input CSV missing | `FileNotFoundError`, error metrics written |
| Unreadable / malformed CSV | `ValueError`, error metrics written |
| Empty CSV | `ValueError`, error metrics written |
| Missing `close` column | `ValueError`, error metrics written |

---

## Reproducibility

Every run with the same `config.yaml` and `data.csv` produces identical
`rows_processed`, `metric`, `value`, `seed`, and `status` fields.
`latency_ms` varies by machine but does not affect signal correctness.
