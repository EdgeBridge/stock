"""Tests for main.py startup initialization order.

Validates that variables are defined before use in the lifespan function.
Catches UnboundLocalError-type bugs like etf_universe used before creation.
"""

import ast
import textwrap

import pytest


def _get_lifespan_source() -> str:
    """Extract the lifespan function source from main.py."""
    with open("main.py") as f:
        source = f.read()
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, ast.AsyncFunctionDef) and node.name == "lifespan":
            return ast.get_source_segment(source, node)
    raise RuntimeError("lifespan function not found in main.py")


def _extract_assignments_and_usages(source: str) -> tuple[dict[str, int], list[tuple[str, int]]]:
    """Extract variable assignment lines and usage lines.

    Only checks top-level statements in the function body — nested functions
    (closures like scheduler tasks) are excluded because they reference
    outer variables at call time, not definition time.

    Returns:
        assignments: {var_name: first_assignment_line}
        usages: [(var_name, usage_line), ...] for key variables
    """
    tree = ast.parse(source)
    assignments: dict[str, int] = {}
    usages: list[tuple[str, int]] = []

    # Key variables whose order matters (heavy dependencies)
    tracked_vars = {
        "etf_universe", "market_data", "kr_market_data", "adapter",
        "kr_adapter", "evaluation_loop", "kr_evaluation_loop",
        "risk_manager", "kr_risk_manager", "order_manager", "kr_order_manager",
        "registry", "config", "scheduler", "notification",
        "market_state_detector", "kr_market_state_detector",
        "etf_engine", "stock_scanner", "sector_analyzer",
        "market_allocator",
    }

    # Collect line ranges of nested function/class definitions to exclude
    nested_ranges: list[tuple[int, int]] = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            # Skip the top-level function itself (the lifespan)
            if node.col_offset > 0 or node.lineno > 1:
                nested_ranges.append((node.lineno, node.end_lineno or 99999))

    def _in_nested(lineno: int) -> bool:
        return any(start <= lineno <= end for start, end in nested_ranges)

    for node in ast.walk(tree):
        if _in_nested(node.lineno if hasattr(node, "lineno") else 0):
            continue
        # Track assignments
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id in tracked_vars:
                    if target.id not in assignments:
                        assignments[target.id] = node.lineno
        # Track usages (Load context only)
        if isinstance(node, ast.Name) and node.id in tracked_vars:
            if isinstance(node.ctx, ast.Load):
                usages.append((node.id, node.lineno))

    return assignments, usages


class TestStartupOrder:
    """Verify that variables in lifespan are defined before use."""

    def test_lifespan_exists(self):
        source = _get_lifespan_source()
        assert "async" in source
        assert len(source) > 100

    def test_no_use_before_assignment(self):
        """Core test: no variable used before it's assigned."""
        source = _get_lifespan_source()
        assignments, usages = _extract_assignments_and_usages(source)

        violations = []
        for var_name, usage_line in usages:
            if var_name in assignments:
                assign_line = assignments[var_name]
                if usage_line < assign_line:
                    violations.append(
                        f"{var_name} used at line {usage_line} "
                        f"but assigned at line {assign_line}"
                    )

        assert violations == [], (
            "Variables used before assignment in lifespan:\n"
            + "\n".join(f"  - {v}" for v in violations)
        )

    def test_etf_universe_before_sector_cache(self):
        """Specific regression test for the etf_universe crash."""
        source = _get_lifespan_source()
        assignments, _ = _extract_assignments_and_usages(source)

        assert "etf_universe" in assignments, "etf_universe not found in lifespan"

        # Find etf_universe.get_all_sectors() usage line
        for i, line in enumerate(source.splitlines(), 1):
            if "etf_universe.get_all_sectors" in line:
                assert i > assignments["etf_universe"], (
                    f"etf_universe.get_all_sectors() at line {i} "
                    f"but etf_universe assigned at line {assignments['etf_universe']}"
                )
                break

    def test_evaluation_loop_before_set_methods(self):
        """evaluation_loop must exist before .set_*() calls."""
        source = _get_lifespan_source()
        assignments, _ = _extract_assignments_and_usages(source)

        assert "evaluation_loop" in assignments
        assign_line = assignments["evaluation_loop"]

        for i, line in enumerate(source.splitlines(), 1):
            if "evaluation_loop.set_" in line:
                assert i > assign_line, (
                    f"evaluation_loop.set_*() at line {i} "
                    f"but evaluation_loop assigned at line {assign_line}"
                )

    def test_risk_manager_before_kelly(self):
        """risk_manager must exist before it's passed to evaluation_loop."""
        source = _get_lifespan_source()
        assignments, _ = _extract_assignments_and_usages(source)

        assert "risk_manager" in assignments
