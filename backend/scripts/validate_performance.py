"""End-to-end validation: compare optimized pipeline against baseline.

Loads baseline-metrics.json and compares against the most recent discovery
runs to measure quality, cost, and latency improvements.

Usage:
    python -m scripts.validate_performance [--baseline-path PATH]
"""
import argparse
import asyncio
import json
import logging
import sys
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger(__name__)

DEFAULT_BASELINE = Path(__file__).parent.parent.parent / "docs" / "superpowers" / "specs" / "baseline-metrics.json"


def load_baseline(path: Path) -> dict:
    if not path.exists():
        logger.error("Baseline file not found at %s. Run capture_baseline.py first.", path)
        sys.exit(1)
    return json.loads(path.read_text())


async def gather_recent_metrics(limit: int = 10) -> list[dict]:
    from scripts.capture_baseline import gather_run_metrics
    return await gather_run_metrics(org_id=None, limit=limit)


def compare_metrics(baseline: dict, current: list[dict]) -> dict:
    """Compare baseline vs current run metrics."""
    current_durations = [m["duration_seconds"] for m in current if m.get("duration_seconds")]
    current_quality = [m["quality_scores"] for m in current if m.get("quality_scores")]

    report = {
        "baseline_run_count": baseline.get("run_count", 0),
        "current_run_count": len(current),
        "duration": {},
        "quality": {},
        "regressions": [],
        "improvements": [],
    }

    bl_avg_dur = baseline.get("avg_duration_seconds")
    if bl_avg_dur and current_durations:
        cur_avg_dur = sum(current_durations) / len(current_durations)
        pct_change = ((cur_avg_dur - bl_avg_dur) / bl_avg_dur) * 100
        report["duration"] = {
            "baseline_avg_s": round(bl_avg_dur, 1),
            "current_avg_s": round(cur_avg_dur, 1),
            "change_pct": round(pct_change, 1),
        }
        if pct_change < -10:
            report["improvements"].append(f"Duration improved by {abs(pct_change):.0f}%")
        elif pct_change > 10:
            report["regressions"].append(f"Duration regressed by {pct_change:.0f}%")

    bl_quality = baseline.get("quality_score_breakdown", {})
    if bl_quality and current_quality:
        all_keys = set(bl_quality.keys())
        for q in current_quality:
            all_keys.update(q.keys())

        for key in sorted(all_keys):
            bl_avg = bl_quality.get(key, {}).get("avg")
            cur_vals = [q.get(key, 0) for q in current_quality if key in q]
            if bl_avg is not None and cur_vals:
                cur_avg = sum(cur_vals) / len(cur_vals)
                delta = cur_avg - bl_avg
                report["quality"][key] = {
                    "baseline_avg": round(bl_avg, 4),
                    "current_avg": round(cur_avg, 4),
                    "delta": round(delta, 4),
                }
                if delta < -0.05:
                    report["regressions"].append(f"Quality metric '{key}' dropped by {abs(delta):.3f}")
                elif delta > 0.05:
                    report["improvements"].append(f"Quality metric '{key}' improved by {delta:.3f}")

    return report


def main():
    parser = argparse.ArgumentParser(description="Validate discovery pipeline performance vs baseline")
    parser.add_argument("--baseline-path", type=str, default=str(DEFAULT_BASELINE))
    parser.add_argument("--limit", type=int, default=10)
    args = parser.parse_args()

    baseline = load_baseline(Path(args.baseline_path))
    current = asyncio.run(gather_recent_metrics(args.limit))

    if not current:
        logger.warning("No recent discovery runs to compare against")
        sys.exit(0)

    report = compare_metrics(baseline, current)

    print("\n" + "=" * 60)
    print("PERFORMANCE VALIDATION REPORT")
    print("=" * 60)

    if report["duration"]:
        d = report["duration"]
        print(f"\nDuration: {d['baseline_avg_s']}s → {d['current_avg_s']}s ({d['change_pct']:+.0f}%)")

    if report["quality"]:
        print("\nQuality Scores:")
        for key, vals in report["quality"].items():
            indicator = "✓" if vals["delta"] >= 0 else "✗"
            print(f"  {indicator} {key}: {vals['baseline_avg']:.3f} → {vals['current_avg']:.3f} ({vals['delta']:+.3f})")

    if report["improvements"]:
        print("\nImprovements:")
        for imp in report["improvements"]:
            print(f"  + {imp}")

    if report["regressions"]:
        print("\nRegressions:")
        for reg in report["regressions"]:
            print(f"  - {reg}")

    if not report["regressions"]:
        print("\nNo quality regressions detected.")

    out_path = Path(args.baseline_path).parent / "validation-report.json"
    out_path.write_text(json.dumps(report, indent=2))
    print(f"\nFull report: {out_path}")


if __name__ == "__main__":
    main()
