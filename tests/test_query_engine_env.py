import pytest

from backend.query_engine import _required_env


def test_required_env_accepts_etl_alias(monkeypatch):
    monkeypatch.delenv("BRAVO_SERVER", raising=False)
    monkeypatch.setenv("BRAVO_SQL_SERVER", "sql.example.internal")

    assert _required_env("BRAVO_SERVER", "BRAVO_SQL_SERVER") == "sql.example.internal"


def test_required_env_does_not_expose_values_when_missing(monkeypatch):
    monkeypatch.delenv("BRAVO_USER", raising=False)
    monkeypatch.delenv("BRAVO_SQL_UID", raising=False)

    with pytest.raises(RuntimeError, match="BRAVO_USER hoac BRAVO_SQL_UID"):
        _required_env("BRAVO_USER", "BRAVO_SQL_UID")
