import importlib.util
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "scripts" / "business_stress_suite.py"
SPEC = importlib.util.spec_from_file_location("business_stress_suite", MODULE_PATH)
suite = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
sys.modules[SPEC.name] = suite
SPEC.loader.exec_module(suite)


def test_catalog_has_90_contiguous_business_cases():
    assert suite.validate_catalog() == []
    assert len(suite.CASES) == 90
    assert [case.id for case in suite.CASES] == [f"Q{i:03d}" for i in range(1, 91)]


def test_every_case_maps_to_read_only_sql():
    for case in suite.CASES:
        checker = suite.CHECKERS[case.checker_id]
        assert checker.database in {"bravo", "local"}
        assert checker.sql.lstrip().upper().startswith(("SELECT", "WITH"))
        assert suite._FORBIDDEN.search(checker.sql) is None


def test_required_high_risk_scenarios_are_covered():
    questions = "\n".join(case.question.lower() for case in suite.CASES)
    assert "doanh thu lớn, nợ quá hạn cao và sức mua giảm" in questions
    assert "tỷ lệ v25 nằm trong bậc có thưởng" in questions
    assert "đánh giá hiệu quả từng chương trình khuyến mãi" in questions
    assert "nguồn nào hiện chưa đủ độ phủ" in questions


def test_markdown_contains_questions_and_direct_sql():
    rendered = suite.render_markdown()
    assert "Q001" in rendered and "Q090" in rendered
    assert "```sql" in rendered
    assert "DMS_DonHangCTKM" in rendered
    assert "fact_congno_khachhang" in rendered
