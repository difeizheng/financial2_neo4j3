import os
import pytest

EXCEL_PATH = os.path.join(
    os.path.dirname(__file__), "..",
    "数字化系统财务模型边界【抽水蓄能】v15(亏损弥补+分红预提税+净资产税+折旧摊销优化）.xlsx"
)


@pytest.fixture(scope="module")
def workbook():
    from parser.excel_reader import parse_workbook
    return parse_workbook(EXCEL_PATH, sheet_names=["参数输入表"])


def test_sheet_parsed(workbook):
    assert len(workbook.sheets) == 1
    assert workbook.sheets[0].id == "参数输入表"


def test_cell_count(workbook):
    cells = workbook.sheets[0]._cells
    # 参数输入表 has 4861 non-empty cells
    assert len(cells) >= 4000


def test_formula_cells_present(workbook):
    cells = workbook.sheets[0]._cells
    formula_cells = [c for c in cells if c.formula_raw]
    # 参数输入表 has 442 formula cells
    assert len(formula_cells) >= 400


def test_cell_ids_unique(workbook):
    cells = workbook.sheets[0]._cells
    ids = [c.id for c in cells]
    assert len(ids) == len(set(ids))


def test_known_cell_i4(workbook):
    cells = workbook.sheets[0]._cells
    cell_map = {c.id: c for c in cells}
    c = cell_map.get("参数输入表_4_I")
    assert c is not None
    assert c.formula_raw == "=ROUNDUP(I10,0)"
    assert "参数输入表_10_I" in c.formula_refs


def test_cross_sheet_formula(workbook):
    cells = workbook.sheets[0]._cells
    cell_map = {c.id: c for c in cells}
    # I14 = =投资概算明细!F24
    c = cell_map.get("参数输入表_14_I")
    assert c is not None
    assert "投资概算明细_24_F" in c.formula_refs


def test_sections_detected(workbook):
    sections = workbook.sheets[0].sections
    assert len(sections) >= 1
    names = [s.name for s in sections]
    assert "工程计划" in names


def test_header_cells(workbook):
    cells = workbook.sheets[0]._cells
    heads = [c for c in cells if c.is_head]
    assert len(heads) >= 5
    values = [c.value for c in heads]
    assert "数值" in values or "参数" in values
