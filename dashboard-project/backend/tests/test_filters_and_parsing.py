import pandas as pd
import pytest
from app.main import _normalize_int_list, _parse_date_components, _apply_filters, _parse_filters

def test_normalize_int_list():
    assert _normalize_int_list(None) == []
    assert _normalize_int_list("") == []
    assert _normalize_int_list([]) == []
    assert _normalize_int_list(2026) == [2026]
    assert _normalize_int_list(2026.0) == [2026]
    assert _normalize_int_list("2026") == [2026]
    assert _normalize_int_list("2025, 2026, 2027") == [2025, 2026, 2027]
    assert _normalize_int_list([2025, "2026"]) == [2025, 2026]
    assert _normalize_int_list("invalid, 2026") == [2026]


def test_parse_date_components_standard_dates():
    dates = pd.Series(["2026-08-15", "2025-01-01", "2024-12-31"])
    y_series, m_series = _parse_date_components(dates)
    assert y_series.tolist() == [2026, 2025, 2024]
    assert m_series.tolist() == [8, 1, 12]


def test_parse_date_components_month_strings():
    dates = pd.Series(["Aug", "September", "5-Jul", "12/2026"])
    y_series, m_series = _parse_date_components(dates, default_year=2026)
    assert m_series.iloc[0] == 8
    assert m_series.iloc[1] == 9
    assert m_series.iloc[2] == 7
    assert m_series.iloc[3] == 12


def test_parse_filters_json():
    assert _parse_filters(None) == {}
    assert _parse_filters("") == {}
    assert _parse_filters('{"team": ["Team A", "Team B"]}') == {"team": ["Team A", "Team B"]}
    assert _parse_filters('invalid json') == {}


def test_apply_filters_multi_year_and_month():
    df = pd.DataFrame({
        "event_date": ["2025-08-01", "2026-08-15", "2026-09-10", "2027-01-05"],
        "team": ["Alpha", "Beta", "Alpha", "Gamma"],
        "vci": ["123", "000456", "789", "000123"]
    })

    # Filter single year
    res_year = _apply_filters(df, "event_date", year=2026, month=None)
    assert len(res_year) == 2

    # Filter multi years as list
    res_multi_year = _apply_filters(df, "event_date", year=[2025, 2026], month=None)
    assert len(res_multi_year) == 3

    # Filter multi years as comma string
    res_str_year = _apply_filters(df, "event_date", year="2025,2026", month=None)
    assert len(res_str_year) == 3

    # Filter multi month
    res_month = _apply_filters(df, "event_date", year=None, month=[8, 9])
    assert len(res_month) == 3

    # Filter categorical multi-select
    res_team = _apply_filters(df, "event_date", year=None, month=None, filters={"team": ["Alpha", "Gamma"]})
    assert len(res_team) == 3
    assert set(res_team["team"]) == {"Alpha", "Gamma"}


def test_apply_filters_vci_padding():
    df = pd.DataFrame({
        "vci": ["1234", "005678", "000999"],
        "val": [10, 20, 30]
    })

    # Unpadded search should match padded in df
    res = _apply_filters(df, None, filters={"vci": ["5678"]})
    assert len(res) == 1
    assert res.iloc[0]["vci"] == "005678"

    # Padded search should match unpadded in df
    res2 = _apply_filters(df, None, filters={"vci": ["001234"]})
    assert len(res2) == 1
    assert res2.iloc[0]["vci"] == "1234"


def test_team_wise_summary_with_list_filters():
    from starlette.testclient import TestClient
    from app.main import app

    client = TestClient(app)
    # Pass list in filters JSON to ensure no TypeError: unhashable type: 'list'
    res = client.get("/api/team-wise-summary?filters=%7B%22team%22%3A%5B%22Team%20A%22%5D%2C%22year%22%3A%5B2026%5D%2C%22month%22%3A%5B8%5D%7D")
    assert res.status_code == 200

