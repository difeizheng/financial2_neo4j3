"""Minimal Excel formula calculation engine for change propagation.

Supports the high-frequency functions found in this financial model.
Cell values are passed in as a flat dict {cell_id: value}.
"""
import datetime
import math
import re
from typing import Any

from parser.formula_parser import parse_formula_refs


# ---------------------------------------------------------------------------
# Helper utilities
# ---------------------------------------------------------------------------

def _num(v: Any) -> float:
    if v is None:
        return 0.0
    if isinstance(v, bool):
        return 1.0 if v else 0.0
    if isinstance(v, (int, float)):
        return float(v)
    try:
        return float(v)
    except (TypeError, ValueError):
        return 0.0


def _to_date(v: Any) -> datetime.date:
    if isinstance(v, datetime.datetime):
        return v.date()
    if isinstance(v, datetime.date):
        return v
    raise ValueError(f"Cannot convert {v!r} to date")


# ---------------------------------------------------------------------------
# Function implementations
# ---------------------------------------------------------------------------

def _fn_sum(args: list) -> float:
    return sum(_num(a) for a in args)


def _fn_round(args: list) -> float:
    val, digits = _num(args[0]), int(_num(args[1]))
    return round(val, digits)


def _fn_roundup(args: list) -> float:
    val, digits = _num(args[0]), int(_num(args[1]))
    factor = 10 ** digits
    return math.ceil(val * factor) / factor


def _fn_rounddown(args: list) -> float:
    val, digits = _num(args[0]), int(_num(args[1]))
    factor = 10 ** digits
    return math.floor(val * factor) / factor


def _fn_if(args: list) -> Any:
    cond, true_val, false_val = args[0], args[1], args[2] if len(args) > 2 else 0
    return true_val if cond else false_val


def _fn_max(args: list) -> float:
    nums = [_num(a) for a in args if a is not None]
    return max(nums) if nums else 0.0


def _fn_min(args: list) -> float:
    nums = [_num(a) for a in args if a is not None]
    return min(nums) if nums else 0.0


def _fn_abs(args: list) -> float:
    return abs(_num(args[0]))


def _fn_datedif(args: list) -> float:
    """DATEDIF(start, end, unit)."""
    start = _to_date(args[0])
    end = _to_date(args[1])
    unit = str(args[2]).upper().strip('"')
    delta = end - start
    if unit == "D":
        return float(delta.days)
    if unit == "M":
        months = (end.year - start.year) * 12 + (end.month - start.month)
        if end.day < start.day:
            months -= 1
        return float(months)
    if unit == "Y":
        years = end.year - start.year
        if (end.month, end.day) < (start.month, start.day):
            years -= 1
        return float(years)
    return float(delta.days)


def _fn_iferror(args: list) -> Any:
    try:
        return args[0]
    except Exception:
        return args[1] if len(args) > 1 else 0


def _fn_sumif(args: list) -> float:
    # SUMIF(range, criteria, sum_range) — simplified: range and sum_range are lists
    rng, criteria, sum_rng = args[0], args[1], args[2] if len(args) > 2 else args[0]
    if not isinstance(rng, list):
        rng = [rng]
    if not isinstance(sum_rng, list):
        sum_rng = [sum_rng]
    total = 0.0
    for i, val in enumerate(rng):
        if val == criteria or str(val) == str(criteria):
            total += _num(sum_rng[i] if i < len(sum_rng) else 0)
    return total


_FUNCTIONS: dict[str, Any] = {
    "SUM": _fn_sum,
    "ROUND": _fn_round,
    "ROUNDUP": _fn_roundup,
    "ROUNDDOWN": _fn_rounddown,
    "IF": _fn_if,
    "MAX": _fn_max,
    "MIN": _fn_min,
    "ABS": _fn_abs,
    "DATEDIF": _fn_datedif,
    "IFERROR": _fn_iferror,
    "SUMIF": _fn_sumif,
}


# ---------------------------------------------------------------------------
# Simple expression evaluator
# ---------------------------------------------------------------------------

class CalcEngine:
    """Evaluate Excel formulas given a snapshot of cell values.

    This is intentionally minimal: it handles arithmetic, cell references,
    and the high-frequency functions listed above. Complex formulas
    (VLOOKUP, INDEX/MATCH, array formulas) return None to signal
    "cannot evaluate — keep existing value".
    """

    def evaluate(self, formula: str, cell_values: dict[str, Any],
                 current_sheet: str) -> Any:
        """Return computed value or None if formula cannot be evaluated."""
        if not formula or not formula.startswith("="):
            return None
        expr = formula[1:]
        try:
            return self._eval_expr(expr, cell_values, current_sheet)
        except Exception:
            return None

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _resolve_ref(self, ref_id: str, cell_values: dict[str, Any]) -> Any:
        return cell_values.get(ref_id)

    def _eval_expr(self, expr: str, cell_values: dict[str, Any],
                   sheet: str) -> Any:
        expr = expr.strip()

        # String literal
        if expr.startswith('"') and expr.endswith('"'):
            return expr[1:-1]

        # Number literal
        try:
            return float(expr) if '.' in expr else int(expr)
        except ValueError:
            pass

        # Cross-sheet single ref: Sheet!A1
        m = re.fullmatch(r"'?([^'!\[\]]+)'?!([A-Z]{1,3})(\d+)", expr)
        if m:
            ref_id = f"{m.group(1)}_{m.group(3)}_{m.group(2)}"
            return self._resolve_ref(ref_id, cell_values)

        # Local single ref: A1
        m = re.fullmatch(r"([A-Z]{1,3})(\d+)", expr)
        if m:
            ref_id = f"{sheet}_{m.group(2)}_{m.group(1)}"
            return self._resolve_ref(ref_id, cell_values)

        # Function call: NAME(args)
        m = re.match(r"^([A-Z][A-Z0-9]*)(\(.*\))$", expr, re.DOTALL)
        if m:
            fn_name = m.group(1)
            args_str = m.group(2)[1:-1]  # strip outer parens
            args = self._split_args(args_str)
            evaluated_args = []
            for a in args:
                a = a.strip()
                expanded = self._expand_range_arg(a, cell_values, sheet)
                if expanded is not None:
                    evaluated_args.extend(expanded)
                else:
                    evaluated_args.append(self._eval_expr(a, cell_values, sheet))
            fn = _FUNCTIONS.get(fn_name)
            if fn:
                return fn(evaluated_args)
            return None  # unsupported function

        # Comparison expression: A1>5, A1=B1, etc.
        cmp_m = re.match(r"^(.+?)(>=|<=|<>|>|<|=)(.+)$", expr)
        if cmp_m:
            lhs = self._eval_expr(cmp_m.group(1).strip(), cell_values, sheet)
            op = cmp_m.group(2)
            rhs = self._eval_expr(cmp_m.group(3).strip(), cell_values, sheet)
            try:
                if op == ">":  return lhs > rhs
                if op == "<":  return lhs < rhs
                if op == ">=": return lhs >= rhs
                if op == "<=": return lhs <= rhs
                if op == "<>": return lhs != rhs
                if op == "=":  return lhs == rhs
            except TypeError:
                return False

        # Arithmetic: try safe eval with cell refs substituted
        return self._eval_arithmetic(expr, cell_values, sheet)

    def _expand_range_arg(self, arg: str, cell_values: dict[str, Any],
                          sheet: str) -> list[Any] | None:
        """If arg is a cell range (A1:B3 or Sheet!A1:B3), return list of values.
        Returns None if arg is not a range expression.
        """
        from parser.formula_parser import (
            col_letter_to_index, index_to_col_letter, _CROSS_SHEET_RANGE, _LOCAL_RANGE
        )
        # Cross-sheet range
        m = re.fullmatch(r"'?([^'!\[\]]+)'?!([A-Z]{1,3})(\d+):([A-Z]{1,3})(\d+)", arg)
        if m:
            ref_sheet = m.group(1)
            c1, r1, c2, r2 = m.group(2), int(m.group(3)), m.group(4), int(m.group(5))
            return self._range_values(ref_sheet, c1, r1, c2, r2, cell_values)
        # Local range
        m = re.fullmatch(r"([A-Z]{1,3})(\d+):([A-Z]{1,3})(\d+)", arg)
        if m:
            c1, r1, c2, r2 = m.group(1), int(m.group(2)), m.group(3), int(m.group(4))
            return self._range_values(sheet, c1, r1, c2, r2, cell_values)
        return None

    def _range_values(self, ref_sheet: str, c1: str, r1: int, c2: str, r2: int,
                      cell_values: dict[str, Any]) -> list[Any]:
        from parser.formula_parser import col_letter_to_index, index_to_col_letter
        ci1, ci2 = col_letter_to_index(c1), col_letter_to_index(c2)
        values = []
        for r in range(r1, r2 + 1):
            for ci in range(ci1, ci2 + 1):
                cid = f"{ref_sheet}_{r}_{index_to_col_letter(ci)}"
                values.append(cell_values.get(cid, 0))
        return values

    def _split_args(self, args_str: str) -> list[str]:
        """Split comma-separated args respecting nested parentheses."""
        args, depth, current = [], 0, []
        for ch in args_str:
            if ch == '(':
                depth += 1
                current.append(ch)
            elif ch == ')':
                depth -= 1
                current.append(ch)
            elif ch == ',' and depth == 0:
                args.append(''.join(current))
                current = []
            else:
                current.append(ch)
        if current:
            args.append(''.join(current))
        return args

    def _eval_arithmetic(self, expr: str, cell_values: dict[str, Any],
                         sheet: str) -> Any:
        """Substitute cell refs and function calls, then evaluate arithmetic."""
        # Replace function calls first (innermost first via repeated substitution)
        result = self._substitute_functions(expr, cell_values, sheet)
        if result is None:
            return None

        # Replace cross-sheet refs
        def replace_cross(m):
            ref_id = f"{m.group(1)}_{m.group(3)}_{m.group(2)}"
            v = cell_values.get(ref_id, 0)
            return str(_num(v))

        substituted = re.sub(
            r"'?([^'!\[\],+\-*/()=<>& ]+)'?!([A-Z]{1,3})(\d+)",
            replace_cross, result
        )

        # Replace local refs
        def replace_local(m):
            ref_id = f"{sheet}_{m.group(2)}_{m.group(1)}"
            v = cell_values.get(ref_id, 0)
            return str(_num(v))

        substituted = re.sub(r"(?<![A-Z])([A-Z]{1,3})(\d+)(?!\d)", replace_local, substituted)

        # Only allow safe arithmetic characters
        if re.search(r"[^0-9+\-*/().\s]", substituted):
            return None

        try:
            return eval(substituted, {"__builtins__": {}})  # noqa: S307
        except Exception:
            return None

    def _substitute_functions(self, expr: str, cell_values: dict[str, Any],
                               sheet: str) -> str | None:
        """Replace all function calls in expr with their numeric results.
        Returns the substituted string, or None if any substitution fails.
        """
        # Iteratively replace innermost function calls (no nested parens in args)
        fn_pattern = re.compile(r"([A-Z][A-Z0-9]*)\(([^()]*)\)")
        max_iter = 20
        for _ in range(max_iter):
            m = fn_pattern.search(expr)
            if not m:
                break
            fn_name = m.group(1)
            args_str = m.group(2)
            args = self._split_args(args_str)
            evaluated_args = []
            for a in args:
                a = a.strip()
                expanded = self._expand_range_arg(a, cell_values, sheet)
                if expanded is not None:
                    evaluated_args.extend(expanded)
                else:
                    evaluated_args.append(self._eval_expr(a, cell_values, sheet))
            fn = _FUNCTIONS.get(fn_name)
            if fn is None:
                return None
            try:
                val = fn(evaluated_args)
                expr = expr[:m.start()] + str(_num(val)) + expr[m.end():]
            except Exception:
                return None
        return expr
