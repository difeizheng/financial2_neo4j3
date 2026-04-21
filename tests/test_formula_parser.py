import pytest
from parser.formula_parser import parse_formula_refs, col_letter_to_index, index_to_col_letter


def test_col_letter_roundtrip():
    assert index_to_col_letter(col_letter_to_index("A")) == "A"
    assert index_to_col_letter(col_letter_to_index("Z")) == "Z"
    assert index_to_col_letter(col_letter_to_index("AA")) == "AA"
    assert index_to_col_letter(col_letter_to_index("BC")) == "BC"


def test_local_single_ref():
    refs = parse_formula_refs("=ROUNDUP(I10,0)", "参数输入表")
    assert "参数输入表_10_I" in refs


def test_local_range_ref():
    refs = parse_formula_refs("=SUM(I14:I23)", "参数输入表")
    assert len(refs) == 10
    assert "参数输入表_14_I" in refs
    assert "参数输入表_23_I" in refs


def test_cross_sheet_single():
    refs = parse_formula_refs("=投资概算明细!F24", "参数输入表")
    assert refs == ["投资概算明细_24_F"]


def test_cross_sheet_in_expression():
    refs = parse_formula_refs("=时间序列!D5+参数输入表!I5", "其他sheet")
    assert "时间序列_5_D" in refs
    assert "参数输入表_5_I" in refs


def test_mixed_formula():
    refs = parse_formula_refs("=ROUND(DATEDIF(I5,I7,\"D\")/365*12,0)", "参数输入表")
    assert "参数输入表_5_I" in refs
    assert "参数输入表_7_I" in refs


def test_no_formula():
    assert parse_formula_refs(None, "参数输入表") == []
    assert parse_formula_refs("建设期", "参数输入表") == []
    assert parse_formula_refs("", "参数输入表") == []


def test_deduplication():
    refs = parse_formula_refs("=I10+I10", "参数输入表")
    assert refs.count("参数输入表_10_I") == 1


def test_2d_range():
    refs = parse_formula_refs("=SUM(B4:C5)", "Sheet1")
    assert "Sheet1_4_B" in refs
    assert "Sheet1_4_C" in refs
    assert "Sheet1_5_B" in refs
    assert "Sheet1_5_C" in refs
    assert len(refs) == 4
