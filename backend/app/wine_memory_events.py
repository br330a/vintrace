"""Histórico persistente do Wine Memory no Orion.

O registro de um alerta usa o limite vigente quando ele ocorreu.
Dessa forma, normalizar os triggers depois não apaga o incidente.
O armazenamento ocorre na própria entidade NGSI-v2 do dispositivo.
"""

import asyncio
from datetime import datetime, timedelta, timezone
from uuid import uuid4
from zoneinfo import ZoneInfo

import httpx

from .config import settings
from .fiware import device_id_to_urn
from .models import EnvironmentalIncident, HistorySeries, WineMemoryResponse


BR_TZ = ZoneInfo("America/Sao_Paulo")
_EVENT_ATTRIBUTE = "wineMemoryEvents"
_EVENT_TYPES = {
    "alertTemp": ("temperature", "Temperatura", " °C"),
    "alertHum": ("humidity", "Umidade", "%"),
    "alertLum": ("luminosity", "Luminosidade", "%"),
}
_locks: dict[str, asyncio.Lock] = {}


def _parse_date(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return parsed.replace(tzinfo=timezone.utc) if parsed.tzinfo is None else parsed
    except (TypeError, ValueError):
        return None


def _base_url(device_id: str) -> str:
    urn = device_id_to_urn(device_id)
    return f"{settings.fiware_base_url.rstrip('/')}/v2/entities/{urn}/attrs"


def _headers() -> dict[str, str]:
    return {
        "Fiware-Service": settings.fiware_service,
        "Fiware-ServicePath": settings.fiware_service_path,
        "Content-Type": "application/json",
        "Accept": "application/json",
    }


async def load_events(device_id: str) -> list[dict]:
    """Retorna eventos registrados; atributo ainda ausente significa lista vazia."""
    async with httpx.AsyncClient(timeout=8.0) as client:
        response = await client.get(
            f"{_base_url(device_id)}/{_EVENT_ATTRIBUTE}",
            headers=_headers(),
            params={"type": settings.entity_type},
        )

    if response.status_code == 404:
        return []

    response.raise_for_status()
    raw = response.json().get("value", [])
    if not isinstance(raw, list):
        raise RuntimeError("Formato inválido de wineMemoryEvents no Orion.")
    return [event for event in raw if isinstance(event, dict)]


async def record_transition(
    device_id: str,
    command: str,
    state: str,
    value: float,
    limit: float,
) -> None:
    """Abre ou fecha ocorrência após confirmar o comando remoto.

    POST /attrs cria o atributo no primeiro registro e o atualiza nas
    gravações seguintes, diferentemente de PATCH, que exige existência.
    """
    if command not in _EVENT_TYPES or state not in ("high", "low", "off"):
        return

    lock = _locks.setdefault(device_id, asyncio.Lock())
    async with lock:
        events = await load_events(device_id)
        now = datetime.now(timezone.utc).isoformat()
        sensor_type, _, _ = _EVENT_TYPES[command]
        opened = [
            e for e in events
            if e.get("type") == sensor_type and e.get("ended_at") is None
        ]

        # Na sincronização inicial OFF, fecha alertas que possam ter
        # ficado abertos após um reinício do backend.
        if state == "off" and not opened:
            return

        # Para o mesmo alerta após um reboot, não duplica a ocorrência.
        if state in ("high", "low") and len(opened) == 1:
            if opened[0].get("direction") == state:
                return

        for event in opened:
            event["ended_at"] = now

        if state != "off":
            events.append({
                "id": uuid4().hex,
                "type": sensor_type,
                "direction": state,
                "started_at": now,
                "ended_at": None,
                "start_value": float(value),
                "limit": float(limit),
            })

        # Mantém um volume pequeno e a janela de interesse, preservando
        # também incidentes em andamento.
        cutoff = datetime.now(timezone.utc) - timedelta(days=31)
        events = [
            e for e in events
            if (e.get("ended_at") is None)
            or (_parse_date(e.get("ended_at")) or cutoff) > cutoff
        ][-300:]

        async with httpx.AsyncClient(timeout=8.0) as client:
            response = await client.post(
                _base_url(device_id),
                params={"type": settings.entity_type},
                headers=_headers(),
                json={_EVENT_ATTRIBUTE: {"type": "StructuredValue", "value": events}},
            )
        response.raise_for_status()


def _format_duration(seconds: int) -> str:
    seconds = max(int(seconds), 0)
    if seconds < 60:
        return f"{seconds}s"
    minutes = seconds // 60
    if minutes < 60:
        return f"{minutes} min"
    return f"{minutes // 60}h {minutes % 60}min"


def _format_date(instant: datetime) -> str:
    return instant.astimezone(BR_TZ).strftime("%d/%m, %H:%M")


def calculate_recorded_wine_memory(
    device_id: str,
    history: HistorySeries,
    events: list[dict],
) -> WineMemoryResponse:
    """Calcula a estabilidade pelo tempo observado e pelos eventos reais.

    Usa a união de intervalos de anomalia para não contar duas vezes
    condições simultâneas. Se não houver período observável, devolve null.
    """
    now = datetime.now(timezone.utc)
    window_start = now - timedelta(days=30)
    points = history.temperature + history.humidity + history.luminosity
    timestamps = sorted(
        dt for point in points
        if (dt := _parse_date(point.timestamp)) is not None
    )
    observed_start = max(window_start, timestamps[0]) if timestamps else None
    observed_end = timestamps[-1] if timestamps else None
    if observed_end and (now - observed_end).total_seconds() < 65:
        observed_end = now

    incidents: list[EnvironmentalIncident] = []
    union_intervals: list[tuple[datetime, datetime]] = []
    full_intervals: list[tuple[datetime, datetime]] = []
    latest: datetime | None = None

    for event in sorted(events, key=lambda event: event.get("started_at", ""), reverse=True):
        kind = event.get("type")
        if kind not in ("temperature", "humidity", "luminosity"):
            continue
        direction = event.get("direction")
        if direction not in ("high", "low"):
            continue
        start = _parse_date(event.get("started_at"))
        end = _parse_date(event.get("ended_at"))
        if start is None or start > now or (end and end < window_start):
            continue
        start_clamped = max(start, window_start)
        real_end = min(end or now, now)
        if real_end < start_clamped:
            continue

        label = {"temperature": "Temperatura", "humidity": "Umidade", "luminosity": "Luminosidade"}[kind]
        unit = " °C" if kind == "temperature" else "%"
        value = float(event.get("start_value", 0.0))
        limit = float(event.get("limit", 0.0))
        threshold_symbol = ">" if direction == "high" else "<"
        direction_label = "alta" if direction == "high" else "baixa"
        still_active = end is None

        incidents.append(EnvironmentalIncident(
            id=len(incidents) + 1,
            type=kind,
            direction=direction,
            title=f"{label} {direction_label}",
            startedAt=_format_date(start),
            endedAt="Em andamento" if still_active else _format_date(end),
            duration=_format_duration(int((real_end - start_clamped).total_seconds())),
            peakValue=f"{round(value, 1)}{unit}",
            description=(
                f"{label} {direction_label}: leitura inicial {round(value, 1)}{unit} "
                f"{threshold_symbol} limite vigente de {round(limit, 1)}{unit}."
            ),
            active=still_active,
        ))
        if latest is None or start > latest:
            latest = start

        if real_end > start_clamped:
            full_intervals.append((start_clamped, real_end))

        if observed_start and observed_end:
            overlap_start = max(start_clamped, observed_start)
            overlap_end = min(real_end, observed_end)
            if overlap_end > overlap_start:
                union_intervals.append((overlap_start, overlap_end))

    def merged_seconds(intervals: list[tuple[datetime, datetime]]) -> float:
        merged: list[tuple[datetime, datetime]] = []
        for start, end in sorted(intervals):
            if merged and start <= merged[-1][1]:
                merged[-1] = (merged[-1][0], max(end, merged[-1][1]))
            else:
                merged.append((start, end))
        return sum((end - start).total_seconds() for start, end in merged)

    union_seconds = merged_seconds(union_intervals)
    exposure_seconds = merged_seconds(full_intervals)

    total_coverage = (
        (observed_end - observed_start).total_seconds()
        if observed_start and observed_end else 0
    )
    stability = (
        round(max(0, 1 - union_seconds / total_coverage) * 100, 6)
        if total_coverage > 0 else None
    )

    return WineMemoryResponse(
        device_id=device_id,
        totalIncidents=len(incidents),
        exposureTime=_format_duration(int(exposure_seconds)),
        lastIncident=_format_date(latest) if latest else "Nenhum",
        stability=stability,
        incidents=incidents,
        sampleCount=len(points),
        source="recorded",
    )
