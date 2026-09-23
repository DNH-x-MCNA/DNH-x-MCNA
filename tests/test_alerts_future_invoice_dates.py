"""Invoice alerts must ignore documents dated after the day of the run."""

import re

import pytest

import src.alerts as alerts
import src.database as database


class _Connection:
    def __init__(self, queries):
        self.queries = queries

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def execute(self, statement, _params):
        self.queries.append(str(statement))
        return _Result()


class _Result:
    def fetchall(self):
        return []


class _Engine:
    def __init__(self, queries):
        self.queries = queries

    def connect(self):
        return _Connection(self.queries)


@pytest.mark.parametrize("alert", [
    alerts.check_customer_churn_alert,
    alerts.check_revenue_concentration_alert,
])
def test_monthly_invoice_alerts_exclude_future_documents(monkeypatch, alert):
    queries = []
    monkeypatch.setattr(database, "_get_bravo_engine", lambda: _Engine(queries))
    monkeypatch.setattr(alerts, "_last_complete_data_day", lambda: None)

    alert()

    assert len(queries) == 1
    sql = queries[0]
    # Both OTC and ETC must exclude future dates in the rows used for the
    # monthly amount. Filtering only MAX(DocDate) still includes future rows.
    for view in ("vHoaDonTotal", "vHoaDonETCTotal"):
        source = re.search(rf"FROM dbo\.{view} v\b(.+?)(?:GROUP BY|UNION ALL)", sql, re.S)
        assert source is not None
        assert "v.DocDate <= CAST(GETDATE() AS DATE)" in source.group(1)


def test_overdue_new_orders_exclude_future_documents_without_until(monkeypatch):
    queries = []
    monkeypatch.setattr(database, "_get_bravo_engine", lambda: _Engine(queries))

    alerts._bravo_recent_orders_by_customer("2026-09-01")

    assert len(queries) == 1
    sql = queries[0]
    assert sql.count("DocDate <= CAST(GETDATE() AS DATE)") == 2
