"""Data analysis tools — pandas-based helpers for the Data specialist."""
from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


class DataAnalysisTool:
    """
    Lightweight data analysis helper for the Data department specialist.
    Accepts a dict of named datasets and returns analysis results.
    """

    def __init__(self) -> None:
        self._pandas_available = self._check_pandas()

    @staticmethod
    def _check_pandas() -> bool:
        try:
            import pandas  # noqa: F401
            return True
        except ImportError:
            logger.warning("pandas not installed — data analysis limited")
            return False

    def analyse(self, data: dict[str, Any]) -> dict[str, Any]:
        """
        Perform basic analysis on a dict of named datasets.
        Returns a summary dict with descriptive stats.
        """
        if not self._pandas_available:
            return {
                "status": "skipped",
                "reason": "pandas not installed",
                "data_keys": list(data.keys()),
            }

        import pandas as pd

        results: dict[str, Any] = {"datasets": {}}

        for name, values in data.items():
            if isinstance(values, list) and values and isinstance(values[0], (int, float)):
                series = pd.Series(values)
                results["datasets"][name] = {
                    "count": int(series.count()),
                    "mean": float(series.mean()),
                    "std": float(series.std()),
                    "min": float(series.min()),
                    "max": float(series.max()),
                    "sum": float(series.sum()),
                }
            elif isinstance(values, list) and values and isinstance(values[0], dict):
                # Treat as rows
                try:
                    df = pd.DataFrame(values)
                    numeric_cols = df.select_dtypes(include="number").columns
                    results["datasets"][name] = {
                        "rows": len(df),
                        "columns": list(df.columns),
                        "numeric_summary": {
                            col: {
                                "mean": float(df[col].mean()),
                                "min": float(df[col].min()),
                                "max": float(df[col].max()),
                            }
                            for col in numeric_cols
                        },
                    }
                except Exception as exc:
                    results["datasets"][name] = {"error": str(exc)}

        logger.info(f"Data analysis complete for {list(results['datasets'].keys())}")
        return results

    def load_file(self, path: str) -> dict[str, Any]:
        """
        Load a CSV or Excel file from disk and return structured analysis.

        Returns a dict with keys:
          path, rows, columns, numeric_columns, summary (per-column stats), sample_rows
        On error, returns {"error": "<msg>", "path": path}.
        """
        import os

        if not self._pandas_available:
            return {"error": "pandas not available", "path": path}

        if not os.path.isfile(path):
            return {"error": f"File not found: {path}", "path": path}

        import pandas as pd

        ext = os.path.splitext(path)[1].lower()
        try:
            if ext == ".csv":
                df = pd.read_csv(path)
            elif ext in (".xlsx", ".xls"):
                df = pd.read_excel(path)
            else:
                return {"error": f"Unsupported file type: {ext}", "path": path}

            numeric_cols = df.select_dtypes(include="number").columns.tolist()
            result: dict[str, Any] = {
                "path": path,
                "rows": len(df),
                "columns": list(df.columns),
                "numeric_columns": numeric_cols,
                "summary": {},
                "sample_rows": df.head(5).fillna("").to_dict(orient="records"),
            }
            for col in numeric_cols:
                result["summary"][col] = {
                    "sum": float(df[col].sum()),
                    "mean": float(df[col].mean()),
                    "min": float(df[col].min()),
                    "max": float(df[col].max()),
                }
            logger.info(
                "Loaded file %s: %d rows, %d numeric columns",
                path, len(df), len(numeric_cols),
            )
            return result
        except Exception as exc:
            logger.error("Failed to load file %s: %s", path, exc)
            return {"error": str(exc), "path": path}

    def compute_roi(
        self,
        revenue: list[float],
        cost: list[float],
    ) -> dict[str, Any]:
        """Compute ROI metrics from revenue and cost arrays."""
        if not self._pandas_available:
            return {"error": "pandas not available"}

        import pandas as pd

        rev = pd.Series(revenue)
        cost_series = pd.Series(cost)
        profit = rev - cost_series
        roi = (profit / cost_series) * 100

        return {
            "total_revenue": float(rev.sum()),
            "total_cost": float(cost_series.sum()),
            "total_profit": float(profit.sum()),
            "avg_roi_pct": float(roi.mean()),
            "roi_series": roi.to_dict(),
        }
