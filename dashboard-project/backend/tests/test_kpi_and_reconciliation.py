import pytest
from app.ingest import sanitize_identifier, sanitize_table_name

def test_sanitize_identifier():
    assert sanitize_identifier("Actual Arrival Date") == "actual_arrival_date"
    assert sanitize_identifier("VIN # (Vehicle ID)") == "vin_vehicle_id"
    assert sanitize_identifier("123 Column Name") == "_123_column_name"
    assert sanitize_identifier("team-name") == "team_name"


def test_sanitize_table_name():
    assert sanitize_table_name("Niv Sheet Arrival (Aug 2026).xlsx") == "niv_sheet_arrival"
    assert sanitize_table_name("Disposal_Tracker_2026.xlsx") == "disposal"
    assert sanitize_table_name("to_be_disposed_data.xlsx") == "to_be_disposed"
    assert sanitize_table_name("Budget Summary Report.xlsx") == "budget"


def test_api_tables_endpoint(client):
    response = client.get("/api/tables")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)


def test_api_glidepath_departments_endpoint(client):
    response = client.get("/api/glidepath/departments")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    if len(data) > 0:
        assert "department_no" in data[0]


def test_api_glidepath_summary_comparison(client):
    response = client.get("/api/glidepath-summary-comparison")
    assert response.status_code == 200
    data = response.json()
    assert "year" in data
    assert "month" in data
    assert "glidepath_arrival" in data
    assert "actual_arrival" in data
    assert "actual_disposal" in data


def test_api_team_wise_summary(client):
    response = client.get("/api/team-wise-summary")
    assert response.status_code == 200
    data = response.json()
    assert "metrics" in data
    assert "teams" in data
    assert "data" in data
    assert "category_totals" in data


def test_api_filters_endpoint(client):
    # Test filters endpoint for a table or 404 for unknown table
    response = client.get("/api/filters/non_existent_table")
    assert response.status_code == 404
