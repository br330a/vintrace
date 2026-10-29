"""Regressões do Wine Memory: nenhum dado, histórico e triggers restaurados."""
import asyncio
from datetime import datetime, timedelta, timezone

from app import wine_memory_events as event_store
from app.fiware import calculate_wine_memory
from app.models import HistoryPoint, HistorySeries, SensorRange, TriggerConfig


def triggers(temp_max=18.0):
    return TriggerConfig(
        temperature=SensorRange(min=10, max=temp_max),
        humidity=SensorRange(min=60, max=80),
        luminosity=SensorRange(min=0, max=20),
    )


def test_without_history_stability_is_unknown():
    result = calculate_wine_memory("vintrace001", HistorySeries(), triggers())
    assert result.stability is None
    assert result.sampleCount == 0
    assert result.source == "estimated"


def test_estimated_wine_memory_detects_history_outside_range():
    history = HistorySeries(temperature=[
        HistoryPoint(time="10:00", value=15),
        HistoryPoint(time="10:05", value=22),
        HistoryPoint(time="10:10", value=15),
    ])
    result = calculate_wine_memory("vintrace001", history, triggers())
    assert result.totalIncidents == 1
    assert result.stability < 100


def test_orion_events_remain_after_limits_are_restored(monkeypatch):
    async def exercise():
        persistent = {}

        class Response:
            def __init__(self, status_code, data=None):
                self.status_code = status_code
                self.data = data or {}
            def json(self):
                return self.data
            def raise_for_status(self):
                assert 200 <= self.status_code < 300, self.status_code

        class FakeClient:
            def __init__(self, **kwargs):
                pass
            async def __aenter__(self):
                return self
            async def __aexit__(self, *args):
                return False
            async def get(self, url, **kwargs):
                if "wineMemoryEvents" not in persistent:
                    return Response(404)
                return Response(200, {"type": "StructuredValue", "value": persistent["wineMemoryEvents"]})
            async def post(self, url, json=None, **kwargs):
                assert json["wineMemoryEvents"]["type"] == "StructuredValue"
                persistent["wineMemoryEvents"] = json["wineMemoryEvents"]["value"]
                return Response(204)

        monkeypatch.setattr(event_store.httpx, "AsyncClient", FakeClient)
        await event_store.record_transition("vintrace001", "alertTemp", "high", 21, 18)
        await event_store.record_transition("vintrace001", "alertTemp", "high", 21, 18)
        events = await event_store.load_events("vintrace001")
        assert len(events) == 1, "O mesmo alerta não deve duplicar depois de reiniciar"
        assert events[0]["limit"] == 18
        assert events[0]["ended_at"] is None

        await asyncio.sleep(0.012)
        # O primeiro ciclo normal após um reboot também precisa fechar o evento.
        await event_store.record_transition("vintrace001", "alertTemp", "off", 21, 25)
        events = await event_store.load_events("vintrace001")
        assert len(events) == 1
        assert events[0]["ended_at"] is not None
        assert events[0]["limit"] == 18, "O histórico não pode usar o limite restaurado de 25"

        now = datetime.now(timezone.utc)
        history = HistorySeries(temperature=[
            HistoryPoint(time="10:00", timestamp=(now - timedelta(minutes=15)).isoformat(), value=15),
            HistoryPoint(time="10:15", timestamp=now.isoformat(), value=21),
        ])
        result = event_store.calculate_recorded_wine_memory("vintrace001", history, events)
        assert result.totalIncidents == 1
        assert result.source == "recorded"
        assert "18" in result.incidents[0].description
        assert result.stability is not None
        assert result.stability < 100

        # OFF repetido no startup não cria novo incidente.
        await event_store.record_transition("vintrace001", "alertTemp", "off", 21, 25)
        assert len(await event_store.load_events("vintrace001")) == 1

    asyncio.run(exercise())

def test_recorded_stability_counts_overlap_once():
    now = datetime.now(timezone.utc)
    start = now - timedelta(minutes=6)
    end = now - timedelta(minutes=4)
    history = HistorySeries(temperature=[
        HistoryPoint(time="09:00", timestamp=(now - timedelta(minutes=10)).isoformat(), value=15),
        HistoryPoint(time="09:10", timestamp=now.isoformat(), value=15),
    ])
    events = [
        {"type":"temperature", "direction":"high", "started_at":start.isoformat(),
         "ended_at":end.isoformat(), "start_value":21, "limit":18},
        {"type":"humidity", "direction":"low", "started_at":start.isoformat(),
         "ended_at":end.isoformat(), "start_value":55, "limit":60},
    ]
    result = event_store.calculate_recorded_wine_memory("vintrace001", history, events)
    assert result.totalIncidents == 2
    assert result.exposureTime == "2 min", "Duas anomalias simultâneas são dois incidentes, não 4 min de exposição"
    assert 79.0 <= result.stability <= 81.0
