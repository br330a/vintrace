import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.triggers_store import delete_device_triggers
from app.models import TriggerConfig, SensorRange, HistorySeries, HistoryPoint
from app.fiware import device_id_to_urn, urn_to_device_id, calculate_wine_memory


client = TestClient(app)


def test_health_endpoint():
    res = client.get("/health")
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "ok"
    assert data["fiware_service"] == "smart"
    assert "api_key" not in data


def test_urn_conversion():
    assert device_id_to_urn("vintrace001") == "urn:ngsi-ld:VinTrace:001"
    assert device_id_to_urn("vintrace002") == "urn:ngsi-ld:VinTrace:002"
    assert urn_to_device_id("urn:ngsi-ld:VinTrace:001") == "vintrace001"


def test_triggers_persistence_and_endpoints():
    dev_id = "test_dev_01"
    # 1. Get default triggers
    res = client.get(f"/devices/{dev_id}/triggers")
    assert res.status_code == 200
    data = res.json()
    assert data["device_id"] == dev_id
    assert data["triggers"]["temperature"]["min"] == 10.0
    assert data["triggers"]["temperature"]["max"] == 18.0

    # 2. Update triggers with valid values
    new_triggers = {
        "temperature": {"min": 12.0, "max": 16.0},
        "humidity": {"min": 65.0, "max": 75.0},
        "luminosity": {"min": 2.0, "max": 15.0},
    }
    res_put = client.put(f"/devices/{dev_id}/triggers", json=new_triggers)
    assert res_put.status_code == 200

    # 3. Read back to confirm persistence
    res_read = client.get(f"/devices/{dev_id}/triggers")
    assert res_read.status_code == 200
    assert res_read.json()["triggers"]["temperature"]["min"] == 12.0
    assert res_read.json()["triggers"]["temperature"]["max"] == 16.0

    # 4. Reject invalid triggers min >= max
    bad_triggers = {
        "temperature": {"min": 20.0, "max": 10.0},
        "humidity": {"min": 65.0, "max": 75.0},
        "luminosity": {"min": 2.0, "max": 15.0},
    }
    res_bad = client.put(f"/devices/{dev_id}/triggers", json=bad_triggers)
    assert res_bad.status_code == 422

    # Clean up
    delete_device_triggers(dev_id)


def test_wine_memory_calculation():
    dev_id = "test_wm_01"
    triggers = TriggerConfig(
        temperature=SensorRange(min=10.0, max=18.0),
        humidity=SensorRange(min=60.0, max=80.0),
        luminosity=SensorRange(min=0.0, max=20.0),
    )
    # Series with one temperature anomaly and one humidity anomaly
    history = HistorySeries(
        temperature=[
            HistoryPoint(time="10:00", value=14.0),
            HistoryPoint(time="10:05", value=21.5),  # spike
            HistoryPoint(time="10:10", value=15.0),
        ],
        humidity=[
            HistoryPoint(time="10:00", value=65.0),
            HistoryPoint(time="10:05", value=68.0),
            HistoryPoint(time="10:10", value=85.0),  # spike
        ],
        luminosity=[
            HistoryPoint(time="10:00", value=5.0),
            HistoryPoint(time="10:05", value=8.0),
            HistoryPoint(time="10:10", value=10.0),
        ],
    )

    wm = calculate_wine_memory(dev_id, history, triggers)
    assert wm.device_id == dev_id
    assert wm.totalIncidents >= 1
    assert wm.stability < 100.0
    assert {incident.direction for incident in wm.incidents} <= {"high", "low"}
    assert any(incident.direction == "high" for incident in wm.incidents)


def test_monitoring_endpoints():
    dev_id = "vintrace_test_monitor"
    # Start monitoring
    res_start = client.post(f"/devices/{dev_id}/monitoring/start")
    assert res_start.status_code == 200
    assert res_start.json()["monitoring"] is True

    # Check status
    res_status = client.get(f"/devices/{dev_id}/monitoring")
    assert res_status.status_code == 200
    assert res_status.json()["is_active"] is True

    # Stop monitoring
    res_stop = client.post(f"/devices/{dev_id}/monitoring/stop")
    assert res_stop.status_code == 200
    assert res_stop.json()["monitoring"] is False

def test_wine_memory_does_not_count_long_data_gaps_as_continuous_exposure():
    triggers = TriggerConfig(
        temperature=SensorRange(min=10.0, max=18.0),
        humidity=SensorRange(min=0.0, max=100.0),
        luminosity=SensorRange(min=0.0, max=100.0),
    )

    # Dois buckets horários anômalos separados por oito horas. O período sem
    # telemetria não deve virar oito horas extras de exposição.
    history = HistorySeries(
        temperature=[
            HistoryPoint(
                time="10:00",
                value=25.0,
                timestamp="2026-10-20T10:00:00-03:00",
                min_value=24.0,
                max_value=26.0,
                samples=10,
            ),
            HistoryPoint(
                time="18:00",
                value=25.0,
                timestamp="2026-10-20T18:00:00-03:00",
                min_value=24.0,
                max_value=26.0,
                samples=10,
            ),
        ]
    )

    wm = calculate_wine_memory("vintrace_gap", history, triggers)

    assert wm.totalIncidents == 1
    assert wm.exposureTime == "2h 0min"
