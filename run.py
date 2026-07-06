import argparse
import json
import logging
import sys
import time
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import yaml


def setup_logging(log_file: str) -> logging.Logger:
    logger = logging.getLogger("mlops_pipeline")
    logger.handlers.clear()
    logger.setLevel(logging.INFO)
    logger.propagate = False

    fmt = logging.Formatter(
        fmt="%(asctime)s | %(levelname)-8s | %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S",
    )

    file_handler = logging.FileHandler(log_file, mode="w")
    file_handler.setFormatter(fmt)

    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(fmt)

    logger.addHandler(file_handler)
    logger.addHandler(console_handler)

    return logger


def load_config(config_path: str) -> dict[str, Any]:
    path = Path(config_path)
    if not path.exists():
        raise FileNotFoundError(f"Config file not found: {config_path}")

    with path.open("r") as f:
        try:
            config = yaml.safe_load(f)
        except yaml.YAMLError as exc:
            raise ValueError(f"Invalid YAML in config: {exc}") from exc

    if not isinstance(config, dict):
        raise ValueError("Config must be a YAML mapping (key: value pairs).")

    return config


def validate_config(config: dict[str, Any]) -> None:
    required = {"seed", "window", "version"}
    missing = required - config.keys()
    if missing:
        raise KeyError(f"Config missing required fields: {missing}")

    if not isinstance(config["seed"], int):
        raise ValueError(f"'seed' must be an integer, got: {config['seed']}")

    if not isinstance(config["window"], int) or config["window"] < 1:
        raise ValueError(f"'window' must be a positive integer, got: {config['window']}")

    if not isinstance(config["version"], str):
        raise ValueError(f"'version' must be a string, got: {config['version']}")


def load_dataset(input_path: str) -> pd.DataFrame:
    path = Path(input_path)
    if not path.exists():
        raise FileNotFoundError(f"Input file not found: {input_path}")

    try:
        df = pd.read_csv(path)
    except Exception as exc:
        raise ValueError(f"Failed to parse CSV: {exc}") from exc

    if df.empty:
        raise ValueError("Input CSV is empty.")

    if "close" not in df.columns:
        raise ValueError(
            f"Required column 'close' not found. Columns present: {df.columns.tolist()}"
        )

    # Coerce close to numeric; non-parseable values become NaN
    df["close"] = pd.to_numeric(df["close"], errors="coerce")

    if df["close"].isnull().all():
        raise ValueError("Column 'close' contains no valid numeric values.")

    return df


def compute_signals(df: pd.DataFrame, window: int) -> pd.DataFrame:
    """close > NaN evaluates to False, so signal=0 for the first window-1 rows."""
    df = df.copy()
    df["rolling_mean"] = df["close"].rolling(window=window).mean()
    df["signal"] = (df["close"] > df["rolling_mean"]).astype(int)

    return df


def build_metrics(
    version: str,
    seed: int,
    rows_processed: int,
    signal_rate: float,
    latency_ms: float,
) -> dict[str, Any]:
    return {
        "version": version,
        "rows_processed": rows_processed,
        "metric": "signal_rate",
        "value": round(signal_rate, 4),
        "latency_ms": round(latency_ms),
        "seed": seed,
        "status": "success",
    }


def write_metrics(metrics: dict[str, Any], output_path: str) -> None:
    with open(output_path, "w") as f:
        json.dump(metrics, f, indent=2)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="MLOps batch pipeline: rolling-mean signal generation."
    )
    parser.add_argument("--input",    required=True, help="Path to input CSV file.")
    parser.add_argument("--config",   required=True, help="Path to YAML config file.")
    parser.add_argument("--output",   required=True, help="Path to write metrics JSON.")
    parser.add_argument("--log-file", required=True, help="Path to write log file.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    logger = setup_logging(args.log_file)

    start_time = time.perf_counter()
    version = "v1"  # fallback before config is loaded

    try:
        logger.info("Job started")
        logger.info("Args: input=%s | config=%s | output=%s | log=%s",
                    args.input, args.config, args.output, args.log_file)

        config = load_config(args.config)
        logger.info("Config loaded from %s", args.config)

        validate_config(config)
        seed    = config["seed"]
        window  = config["window"]
        version = config["version"]
        logger.info("Config validated — seed=%d | window=%d | version=%s",
                    seed, window, version)

        np.random.seed(seed)

        df = load_dataset(args.input)
        logger.info("Dataset loaded from %s — %d rows", args.input, len(df))

        df = compute_signals(df, window)
        logger.info("Rolling mean computed (window=%d) — all %d rows retained",
                    window, len(df))

        signal_rate = df["signal"].mean()
        logger.info("Signal generation complete — signal_rate=%.4f", signal_rate)

        elapsed_ms = (time.perf_counter() - start_time) * 1000
        metrics = build_metrics(
            version=version,
            seed=seed,
            rows_processed=len(df),
            signal_rate=signal_rate,
            latency_ms=elapsed_ms,
        )

        write_metrics(metrics, args.output)
        logger.info("Metrics written to %s", args.output)
        logger.info("Job completed successfully | status=success | latency_ms=%.1f", elapsed_ms)

    except Exception as exc:
        elapsed_ms = (time.perf_counter() - start_time) * 1000
        logger.exception("Job failed: %s", exc)

        error_metrics = {
            "version": version,
            "status": "error",
            "error_message": str(exc),
        }
        write_metrics(error_metrics, args.output)
        logger.info("Error metrics written to %s", args.output)

        sys.exit(1)

    print(json.dumps(metrics, indent=2))  # Docker spec requires stdout


if __name__ == "__main__":
    main()
