"""Compare two pattern snapshots produced by analyze_trade_patterns.py.

Used for Phase 2 monitoring — every week, run analyze_trade_patterns.py
and save the output to data/pattern_snapshots/<date>.txt, then run this
script to see if SMALL_WIN_BIG_LOSS / GAVE_BACK / EARLY_EXIT have moved
in the right direction since the baseline.

Usage:
    cd backend && ../venv/bin/python scripts/compare_pattern_snapshots.py \\
        ../data/pattern_snapshots/baseline_2026-04-09.txt \\
        ../data/pattern_snapshots/week1_2026-04-16.txt

Success criteria after 1 week (Phase 1 deploy 2026-04-09):
    SMALL_WIN_BIG_LOSS  : 12.8% → < 5%
    GAVE_BACK           : 20.5% → < 10%
    CAUGHT_BURST_OK     : 12.8% → > 25%
    Average PnL/trade   : improvement
"""

import argparse
import re
import sys
from pathlib import Path


PATTERN_RE = re.compile(
    r"^(?P<label>[A-Z_]+)\s+(?P<count>\d+)\s+(?P<pct>[\d.]+)%\s+"
    r"(?P<total>[+-]?[\d.]+)%\s+(?P<avg>[+-]?[\d.]+)%"
)

STRATEGY_RE = re.compile(
    r"^(?P<name>\w+)\s+(?P<trades>\d+)\s+(?P<wins>\d+)\s+(?P<losses>\d+)\s+"
    r"(?P<avg>[+-]?[\d.]+)%\s+(?P<best>[+-]?[\d.]+)%\s+(?P<worst>[+-]?[\d.]+)%"
)


def parse_snapshot(path: Path) -> dict:
    text = path.read_text()
    patterns: dict[str, dict] = {}
    strategies: dict[str, dict] = {}
    in_pattern_block = False
    in_strategy_block = False

    for line in text.splitlines():
        if "Pattern aggregate:" in line:
            in_pattern_block = True
            in_strategy_block = False
            continue
        if "Per-buy-strategy summary:" in line:
            in_pattern_block = False
            in_strategy_block = True
            continue
        if line.startswith("─") or line.startswith("="):
            continue

        if in_pattern_block:
            m = PATTERN_RE.search(line)
            if m:
                patterns[m["label"]] = {
                    "count": int(m["count"]),
                    "pct": float(m["pct"]),
                    "total_pnl": float(m["total"]),
                    "avg_pnl": float(m["avg"]),
                }
        elif in_strategy_block:
            m = STRATEGY_RE.search(line)
            if m:
                strategies[m["name"]] = {
                    "trades": int(m["trades"]),
                    "wins": int(m["wins"]),
                    "losses": int(m["losses"]),
                    "avg_pnl": float(m["avg"]),
                    "best": float(m["best"]),
                    "worst": float(m["worst"]),
                }
    return {"patterns": patterns, "strategies": strategies}


def diff_pct(a: float | None, b: float | None) -> str:
    if a is None or b is None:
        return "  -  "
    d = b - a
    sign = "+" if d >= 0 else ""
    return f"{sign}{d:>5.1f}"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("baseline", type=Path)
    parser.add_argument("current", type=Path)
    args = parser.parse_args()

    base = parse_snapshot(args.baseline)
    cur = parse_snapshot(args.current)

    print("=" * 90)
    print(f"  Pattern Snapshot Comparison")
    print(f"  Baseline: {args.baseline.name}")
    print(f"  Current : {args.current.name}")
    print("=" * 90)

    # Pattern table
    print(f"\n{'Pattern':<26} {'baseline':>20} {'current':>20} {'Δ pct':>8} {'Δ avg':>8}")
    print("-" * 90)
    all_labels = sorted(set(base["patterns"]) | set(cur["patterns"]))
    target_labels = [
        "CAUGHT_BURST_OK", "EARLY_EXIT", "GAVE_BACK",
        "SMALL_WIN_BIG_LOSS", "FLAT_NEVER_MOVED", "OTHER",
        "CLEAN_LOSS_NEVER_WORKED",
    ]
    for label in target_labels + [l for l in all_labels if l not in target_labels]:
        b = base["patterns"].get(label)
        c = cur["patterns"].get(label)
        bs = f"{b['count']:>4}/{b['pct']:>4.1f}% ({b['avg_pnl']:+5.2f})" if b else "          -        "
        cs = f"{c['count']:>4}/{c['pct']:>4.1f}% ({c['avg_pnl']:+5.2f})" if c else "          -        "
        delta_pct = diff_pct(b["pct"] if b else None, c["pct"] if c else None)
        delta_avg = diff_pct(b["avg_pnl"] if b else None, c["avg_pnl"] if c else None)
        marker = ""
        if label in ("CAUGHT_BURST_OK",) and b and c and c["pct"] > b["pct"]:
            marker = " ✓"
        elif label in ("SMALL_WIN_BIG_LOSS", "GAVE_BACK") and b and c and c["pct"] < b["pct"]:
            marker = " ✓"
        elif label in ("SMALL_WIN_BIG_LOSS", "GAVE_BACK") and b and c and c["pct"] > b["pct"]:
            marker = " ✗"
        print(f"{label:<26} {bs:>20} {cs:>20} {delta_pct:>8} {delta_avg:>8}{marker}")

    # Success criteria evaluation
    print("\nPhase 1 success criteria (1 week target):")
    criteria = [
        ("SMALL_WIN_BIG_LOSS", "<", 5.0),
        ("GAVE_BACK", "<", 10.0),
        ("CAUGHT_BURST_OK", ">", 25.0),
    ]
    for label, op, target in criteria:
        c = cur["patterns"].get(label, {})
        cur_pct = c.get("pct", 0)
        if op == "<":
            status = "✓ PASS" if cur_pct < target else "✗ FAIL"
        else:
            status = "✓ PASS" if cur_pct > target else "✗ FAIL"
        print(f"  {label:<26}  current={cur_pct:>5.1f}%  target {op} {target}%  {status}")

    # Strategy table
    print("\n\nStrategy contribution (avg PnL per trade):")
    print(f"{'Strategy':<26} {'base trades':>13} {'cur trades':>12} {'Δ avg%':>10}")
    print("-" * 80)
    all_strats = sorted(set(base["strategies"]) | set(cur["strategies"]))
    for s in all_strats:
        b = base["strategies"].get(s)
        c = cur["strategies"].get(s)
        bt = f"{b['trades']} ({b['avg_pnl']:+.2f})" if b else "    -    "
        ct = f"{c['trades']} ({c['avg_pnl']:+.2f})" if c else "    -    "
        delta = diff_pct(b["avg_pnl"] if b else None, c["avg_pnl"] if c else None)
        print(f"{s:<26} {bt:>13} {ct:>12} {delta:>10}")


if __name__ == "__main__":
    main()
