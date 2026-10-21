"""Camada de integração FIWARE do VinTrace.

Integra:
- Orion Context Broker (1026)
- IoT Agent UltraLight (4041)
- STH-Comet (8666)

O backend não publica comandos MQTT diretamente. O fluxo de comando final é:
FastAPI -> Orion -> IoT Agent -> MQTT -> ESP32.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from math import ceil
from statistics import median
from typing import Any
from zoneinfo import ZoneInfo

import httpx

from .config import settings
from .models import (
    CurrentReading,
    DeviceItem,
    EnvironmentalIncident,
    HistoryPoint,
    HistorySeries,
    TriggerConfig,
    WineMemoryResponse,
)


BR_TZ = ZoneInfo("America/Sao_Paulo")


def device_id_to_urn(device_id: str) -> str:
    """Converte vintrace001 em urn:ngsi-ld:VinTrace:001."""
    if device_id.startswith("urn:ngsi-ld:"):
        return device_id

    dev_lower = device_id.lower()

    if dev_lower.startswith("vintrace"):
        suffix = device_id[len("vintrace"):]
        if suffix:
            return f"urn:ngsi-ld:VinTrace:{suffix}"

    return f"urn:ngsi-ld:VinTrace:{device_id}"


def urn_to_device_id(urn: str) -> str:
    """Converte urn:ngsi-ld:VinTrace:001 em vintrace001."""
    if ":" not in urn:
        return urn

    suffix = urn.split(":")[-1]

    if suffix.isdigit():
        return f"vintrace{suffix}"

    return suffix


def _fiware_headers(content_type: bool = False) -> dict[str, str]:
    headers = {
        "Fiware-Service": settings.fiware_service,
        "Fiware-ServicePath": settings.fiware_service_path,
        "Accept": "application/json",
    }

    if content_type:
        headers["Content-Type"] = "application/json"

    return headers


def _parse_datetime(value: str | None) -> datetime | None:
    if not value:
        return None

    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed
    except (TypeError, ValueError):
        return None


def _sensor_last_update(entity: dict[str, Any]) -> datetime | None:
    dates: list[datetime] = []

    for attr_name in ("temperature", "humidity", "luminosity"):
        attr = entity.get(attr_name)

        if not isinstance(attr, dict):
            continue

        metadata = attr.get("metadata", {})
        time_instant = metadata.get("TimeInstant")

        if isinstance(time_instant, dict):
            raw_value = time_instant.get("value")
        else:
            raw_value = time_instant

        parsed = _parse_datetime(raw_value)

        if parsed:
            dates.append(parsed)

    return max(dates) if dates else None


def _device_is_online(entity: dict[str, Any]) -> bool:
    last_update = _sensor_last_update(entity)

    if not last_update:
        return False

    elapsed = (
        datetime.now(timezone.utc)
        - last_update.astimezone(timezone.utc)
    ).total_seconds()

    return elapsed <= 60


def _entity_number(entity: dict[str, Any], name: str) -> float:
    attr = entity.get(name)

    if not isinstance(attr, dict):
        return 0.0

    try:
        return float(attr.get("value", 0.0))
    except (TypeError, ValueError):
        return 0.0


def _entity_text(
    entity: dict[str, Any],
    name: str,
    default: str,
) -> str:
    attr = entity.get(name)

    if not isinstance(attr, dict):
        return default

    value = attr.get("value")
    return str(value) if value not in (None, "") else default


async def check_fiware_health() -> dict[str, Any]:
    """Verifica Orion, IoT Agent e STH-Comet."""
    results: dict[str, Any] = {
        "orion": {
            "status": "offline",
            "url": settings.fiware_base_url,
            "details": None,
        },
        "iot_agent": {
            "status": "offline",
            "url": settings.iot_agent_url,
            "details": None,
        },
        "sth_comet": {
            "status": "offline",
            "url": settings.sth_comet_url,
            "details": None,
        },
        "overall": "degraded",
    }

    async with httpx.AsyncClient(timeout=4.0) as client:
        try:
            response = await client.get(
                f"{settings.fiware_base_url.rstrip('/')}/version"
            )
            if response.status_code == 200:
                results["orion"] = {
                    "status": "online",
                    "url": settings.fiware_base_url,
                    "details": response.json(),
                }
        except Exception as exc:
            results["orion"]["details"] = str(exc)

        try:
            response = await client.get(
                f"{settings.iot_agent_url.rstrip('/')}/iot/about"
            )

            if response.status_code != 200:
                response = await client.get(
                    f"{settings.iot_agent_url.rstrip('/')}/version"
                )

            if response.status_code == 200:
                results["iot_agent"] = {
                    "status": "online",
                    "url": settings.iot_agent_url,
                    "details": response.json(),
                }
        except Exception as exc:
            results["iot_agent"]["details"] = str(exc)

        try:
            response = await client.get(
                f"{settings.sth_comet_url.rstrip('/')}/version"
            )
            if response.status_code == 200:
                results["sth_comet"] = {
                    "status": "online",
                    "url": settings.sth_comet_url,
                    "details": response.json(),
                }
        except Exception as exc:
            results["sth_comet"]["details"] = str(exc)

    online_count = sum(
        1
        for key in ("orion", "iot_agent", "sth_comet")
        if results[key]["status"] == "online"
    )

    if online_count == 3:
        results["overall"] = "healthy"
    elif online_count == 0:
        results["overall"] = "unreachable"
    else:
        results["overall"] = "partial"

    return results


async def register_device_fiware(
    device_id: str,
    name: str,
    location: str,
) -> dict[str, Any]:
    """Provisiona um dispositivo real no IoT Agent UltraLight."""
    urn = device_id_to_urn(device_id)
    headers = _fiware_headers(content_type=True)

    iot_payload = {
        "devices": [
            {
                "device_id": device_id,
                "entity_name": urn,
                "entity_type": settings.entity_type,
                "protocol": "PDI-IoTA-UltraLight",
                "transport": "MQTT",
                "apikey": settings.fiware_api_key,
                "timezone": "America/Sao_Paulo",
                "attributes": [
                    {
                        "object_id": "t",
                        "name": "temperature",
                        "type": "Number",
                    },
                    {
                        "object_id": "h",
                        "name": "humidity",
                        "type": "Number",
                    },
                    {
                        "object_id": "l",
                        "name": "luminosity",
                        "type": "Number",
                    },
                ],
                "commands": [
                    {"name": "alertTemp", "type": "command"},
                    {"name": "alertHum", "type": "command"},
                    {"name": "alertLum", "type": "command"},
                ],
                "static_attributes": [
                    {"name": "name", "type": "Text", "value": name},
                    {
                        "name": "location",
                        "type": "Text",
                        "value": location,
                    },
                    {
                        "name": "deviceId",
                        "type": "Text",
                        "value": device_id,
                    },
                ],
            }
        ]
    }

    async with httpx.AsyncClient(timeout=8.0) as client:
        iot_url = f"{settings.iot_agent_url.rstrip('/')}/iot/devices"

        try:
            iot_response = await client.post(
                iot_url,
                headers=headers,
                json=iot_payload,
            )
        except httpx.HTTPError as exc:
            raise RuntimeError(
                f"IoT Agent indisponível durante o cadastro: {exc}"
            ) from exc

        if iot_response.status_code == 409:
            raise ValueError(
                f"O dispositivo '{device_id}' já está cadastrado no IoT Agent."
            )

        if iot_response.status_code not in (200, 201, 204):
            raise RuntimeError(
                "Falha ao cadastrar dispositivo no IoT Agent: "
                f"HTTP {iot_response.status_code} - "
                f"{iot_response.text[:250]}"
            )

        metadata_payload = {
            "name": {"type": "Text", "value": name},
            "location": {"type": "Text", "value": location},
            "deviceId": {"type": "Text", "value": device_id},
        }

        attrs_url = (
            f"{settings.fiware_base_url.rstrip('/')}"
            f"/v2/entities/{urn}/attrs?type={settings.entity_type}"
        )

        try:
            metadata_response = await client.patch(
                attrs_url,
                headers=headers,
                json=metadata_payload,
            )
        except httpx.HTTPError as exc:
            raise RuntimeError(
                f"Orion indisponível durante o cadastro: {exc}"
            ) from exc

        if metadata_response.status_code == 404:
            create_url = f"{settings.fiware_base_url.rstrip('/')}/v2/entities"
            create_payload = {
                "id": urn,
                "type": settings.entity_type,
                **metadata_payload,
                "temperature": {"type": "Number", "value": 0.0},
                "humidity": {"type": "Number", "value": 0.0},
                "luminosity": {"type": "Number", "value": 0.0},
            }

            create_response = await client.post(
                create_url,
                headers=headers,
                json=create_payload,
            )

            if create_response.status_code not in (200, 201, 204):
                raise RuntimeError(
                    "Dispositivo foi provisionado no IoT Agent, mas a entidade "
                    "não pôde ser criada no Orion: "
                    f"HTTP {create_response.status_code} - "
                    f"{create_response.text[:250]}"
                )

        elif metadata_response.status_code not in (200, 204):
            raise RuntimeError(
                "Dispositivo foi provisionado no IoT Agent, mas os metadados "
                "não puderam ser atualizados no Orion: "
                f"HTTP {metadata_response.status_code} - "
                f"{metadata_response.text[:250]}"
            )

    return {
        "device_id": device_id,
        "entity_urn": urn,
        "name": name,
        "location": location,
        "registered": True,
        "transport": "MQTT",
        "protocol": "PDI-IoTA-UltraLight",
    }


async def delete_device_fiware(device_id: str) -> bool:
    """Remove o dispositivo do IoT Agent e do Orion.

    HTTP 404 é tolerado para permitir limpeza idempotente.
    Qualquer outro erro é propagado ao frontend.
    """
    urn = device_id_to_urn(device_id)
    headers = _fiware_headers()

    async with httpx.AsyncClient(timeout=6.0) as client:
        iot_url = f"{settings.iot_agent_url.rstrip('/')}/iot/devices/{device_id}"
        orion_url = (
            f"{settings.fiware_base_url.rstrip('/')}"
            f"/v2/entities/{urn}?type={settings.entity_type}"
        )

        try:
            iot_response = await client.delete(iot_url, headers=headers)
        except httpx.HTTPError as exc:
            raise RuntimeError(
                f"Falha ao acessar IoT Agent durante exclusão: {exc}"
            ) from exc

        if iot_response.status_code not in (200, 204, 404):
            raise RuntimeError(
                "Falha ao excluir dispositivo do IoT Agent: "
                f"HTTP {iot_response.status_code} - "
                f"{iot_response.text[:250]}"
            )

        try:
            orion_response = await client.delete(orion_url, headers=headers)
        except httpx.HTTPError as exc:
            raise RuntimeError(
                f"Falha ao acessar Orion durante exclusão: {exc}"
            ) from exc

        if orion_response.status_code not in (200, 204, 404):
            raise RuntimeError(
                "Falha ao excluir entidade do Orion: "
                f"HTTP {orion_response.status_code} - "
                f"{orion_response.text[:250]}"
            )

    return True


async def list_devices_fiware() -> list[DeviceItem]:
    """Lista somente entidades reais do Orion."""
    headers = _fiware_headers()
    orion_url = (
        f"{settings.fiware_base_url.rstrip('/')}"
        f"/v2/entities?type={settings.entity_type}&limit=100"
    )

    try:
        async with httpx.AsyncClient(timeout=6.0) as client:
            response = await client.get(orion_url, headers=headers)
            response.raise_for_status()
    except httpx.HTTPError as exc:
        raise RuntimeError(f"Falha ao consultar dispositivos no Orion: {exc}") from exc

    entities = response.json()
    items: list[DeviceItem] = []

    for entity in entities:
        urn = entity.get("id", "")
        device_id = _entity_text(
            entity,
            "deviceId",
            urn_to_device_id(urn),
        )

        # Compatibilidade com o primeiro provisionamento físico, que usava
        # label/place, e com os novos cadastros que usam name/location.
        name = _entity_text(
            entity,
            "name",
            _entity_text(entity, "label", device_id),
        )
        location = _entity_text(
            entity,
            "location",
            _entity_text(entity, "place", "Laboratório"),
        )

        items.append(
            DeviceItem(
                id=device_id,
                name=name,
                location=location,
                online=_device_is_online(entity),
                temperature=round(_entity_number(entity, "temperature"), 1),
                humidity=round(_entity_number(entity, "humidity"), 1),
                luminosity=round(_entity_number(entity, "luminosity"), 1),
            )
        )

    return items


async def get_current_reading(device_id: str) -> CurrentReading:
    """Consulta a leitura atual no Orion."""
    urn = device_id_to_urn(device_id)
    headers = _fiware_headers()
    orion_url = (
        f"{settings.fiware_base_url.rstrip('/')}"
        f"/v2/entities/{urn}?type={settings.entity_type}"
    )

    async with httpx.AsyncClient(timeout=6.0) as client:
        response = await client.get(orion_url, headers=headers)

    if response.status_code == 404:
        raise ValueError(
            f"Dispositivo '{device_id}' ({urn}) não encontrado no Orion."
        )

    response.raise_for_status()
    entity = response.json()

    alerts: dict[str, bool] = {
        "alertTemp": False,
        "alertHum": False,
        "alertLum": False,
    }

    for command in alerts:
        attr = entity.get(command)

        if not isinstance(attr, dict):
            continue

        value = str(attr.get("value", "")).strip().lower()
        alerts[command] = value in {
            "on",
            "high",
            "low",
            "true",
            "1",
        }

    last_update = _sensor_last_update(entity)
    reading_timestamp = (
        last_update.astimezone(BR_TZ).isoformat()
        if last_update
        else datetime.now(BR_TZ).isoformat()
    )

    return CurrentReading(
        device_id=device_id,
        entity_urn=urn,
        timestamp=reading_timestamp,
        temperature=round(_entity_number(entity, "temperature"), 1),
        humidity=round(_entity_number(entity, "humidity"), 1),
        luminosity=round(_entity_number(entity, "luminosity"), 1),
        online=_device_is_online(entity),
        status="Alerta" if any(alerts.values()) else "Normal",
        alerts=alerts,
        raw=entity,
    )


async def send_fiware_command(
    device_id: str,
    command: str,
    value: str = "off",
) -> dict[str, Any]:
    """Envia comando exclusivamente pelo fluxo Orion -> IoT Agent -> MQTT."""
    allowed_commands = {"alertTemp", "alertHum", "alertLum"}
    allowed_values = {"high", "low", "off"}

    if command not in allowed_commands:
        raise ValueError(f"Comando FIWARE inválido: {command}")

    if value not in allowed_values:
        raise ValueError(f"Valor de comando inválido: {value}")

    urn = device_id_to_urn(device_id)
    url = (
        f"{settings.fiware_base_url.rstrip('/')}"
        f"/v2/entities/{urn}/attrs"
    )
    payload = {
        command: {
            "type": "command",
            "value": value,
        }
    }

    try:
        async with httpx.AsyncClient(timeout=6.0) as client:
            response = await client.patch(
                url,
                headers=_fiware_headers(content_type=True),
                json=payload,
            )
    except httpx.HTTPError as exc:
        raise RuntimeError(
            f"Falha de comunicação com Orion ao enviar comando: {exc}"
        ) from exc

    if response.status_code not in (200, 204):
        raise RuntimeError(
            "Orion não aceitou o comando remoto: "
            f"HTTP {response.status_code} - {response.text[:250]}"
        )

    return {
        "device_id": device_id,
        "command": command,
        "value": value,
        "sent_via": "orion",
        "status": "dispatched",
    }


def _period_delta(period: str) -> timedelta:
    return {
        "24h": timedelta(hours=24),
        "7d": timedelta(days=7),
        "30d": timedelta(days=30),
    }.get(period, timedelta(hours=24))


def _aggregation_period(period: str) -> str:
    return {
        "24h": settings.sth_24h_period,
        "7d": settings.sth_7d_period,
        "30d": settings.sth_30d_period,
    }.get(period, settings.sth_24h_period)


def _format_history_time(dt: datetime, period: str) -> str:
    local_dt = dt.astimezone(BR_TZ)

    if period == "24h":
        return local_dt.strftime("%H:%M")

    if period == "7d":
        return local_dt.strftime("%d/%m %Hh")

    return local_dt.strftime("%d/%m %Hh")


def _extract_v1_values(raw_data: dict[str, Any]) -> list[dict[str, Any]]:
    context_responses = raw_data.get("contextResponses", [])

    if not context_responses:
        return []

    context_element = context_responses[0].get("contextElement", {})
    attributes = context_element.get("attributes", [])

    if not attributes:
        return []

    values = attributes[0].get("values", [])
    return values if isinstance(values, list) else []


def _parse_sth_raw_values(
    raw_data: dict[str, Any],
    period: str,
) -> list[HistoryPoint]:
    points: list[HistoryPoint] = []

    for item in _extract_v1_values(raw_data):
        raw_value = item.get("attrValue")
        recv_time = item.get("recvTime")

        try:
            value = float(raw_value)
        except (TypeError, ValueError):
            continue

        dt = _parse_datetime(recv_time)

        if not dt:
            continue

        local_dt = dt.astimezone(BR_TZ)
        points.append(
            HistoryPoint(
                time=_format_history_time(dt, period),
                value=round(value, 1),
                timestamp=local_dt.isoformat(),
                min_value=round(value, 1),
                max_value=round(value, 1),
                samples=1,
            )
        )

    return points


def _offset_datetime(
    origin: datetime,
    resolution: str,
    offset: int,
) -> datetime:
    if resolution == "second":
        return origin + timedelta(seconds=offset)
    if resolution == "minute":
        return origin + timedelta(minutes=offset)
    if resolution == "hour":
        return origin + timedelta(hours=offset)
    if resolution == "day":
        return origin + timedelta(days=offset)

    # Para month o offset é tratado como dias apenas como fallback.
    return origin + timedelta(days=offset)


def _parse_sth_aggregated_values(
    raw_data: dict[str, Any],
    period: str,
) -> list[HistoryPoint]:
    result: list[HistoryPoint] = []

    for group in _extract_v1_values(raw_data):
        identifier = group.get("_id", {})
        origin = _parse_datetime(identifier.get("origin"))
        resolution = str(identifier.get("resolution", ""))
        bucket_points = group.get("points", [])

        if not origin or not isinstance(bucket_points, list):
            continue

        for item in bucket_points:
            try:
                offset = int(item.get("offset", 0))
                samples = int(item.get("samples", 0))
            except (TypeError, ValueError):
                continue

            raw_sum = item.get("sum")
            raw_min = item.get("min")
            raw_max = item.get("max")

            try:
                minimum = float(raw_min)
                maximum = float(raw_max)
            except (TypeError, ValueError):
                continue

            if samples > 0 and raw_sum is not None:
                try:
                    average = float(raw_sum) / samples
                except (TypeError, ValueError, ZeroDivisionError):
                    average = (minimum + maximum) / 2
            else:
                average = (minimum + maximum) / 2

            dt = _offset_datetime(origin, resolution, offset)
            local_dt = dt.astimezone(BR_TZ)

            result.append(
                HistoryPoint(
                    time=_format_history_time(dt, period),
                    value=round(average, 1),
                    timestamp=local_dt.isoformat(),
                    min_value=round(minimum, 1),
                    max_value=round(maximum, 1),
                    samples=max(samples, 1),
                )
            )

    return result


def _sort_and_dedupe(points: list[HistoryPoint]) -> list[HistoryPoint]:
    by_timestamp: dict[str, HistoryPoint] = {}

    for point in points:
        key = point.timestamp or point.time
        by_timestamp[key] = point

    return sorted(
        by_timestamp.values(),
        key=lambda point: point.timestamp or point.time,
    )


async def _fetch_raw_sampled_history(
    client: httpx.AsyncClient,
    url: str,
    headers: dict[str, str],
    period: str,
    date_from: str,
    date_to: str,
) -> list[HistoryPoint]:
    """Fallback que amostra páginas ao longo do período inteiro."""
    page_size = min(max(settings.sth_page_size, 1), 100)
    max_points = max(settings.sth_fallback_max_points, page_size)

    first_params = {
        "hLimit": page_size,
        "hOffset": 0,
        "count": "true",
        "dateFrom": date_from,
        "dateTo": date_to,
    }

    first_response = await client.get(
        url,
        headers=headers,
        params=first_params,
    )

    if first_response.status_code == 404:
        return []

    first_response.raise_for_status()
    points = _parse_sth_raw_values(first_response.json(), period)

    try:
        total_count = int(first_response.headers.get("Fiware-Total-Count", "0"))
    except ValueError:
        total_count = 0

    if total_count <= page_size:
        return _sort_and_dedupe(points)

    if total_count <= max_points:
        offsets = list(range(page_size, total_count, page_size))
    else:
        page_count = max(2, ceil(max_points / page_size))
        max_offset = max(total_count - page_size, 0)
        offsets = sorted(
            {
                round(index * max_offset / (page_count - 1))
                for index in range(1, page_count)
            }
        )

    for offset in offsets:
        response = await client.get(
            url,
            headers=headers,
            params={
                "hLimit": page_size,
                "hOffset": offset,
                "dateFrom": date_from,
                "dateTo": date_to,
            },
        )

        if response.status_code == 404:
            continue

        response.raise_for_status()
        points.extend(_parse_sth_raw_values(response.json(), period))

    return _sort_and_dedupe(points)


async def fetch_sth_history(
    device_id: str,
    period: str = "24h",
) -> HistorySeries:
    """Consulta o período completo no STH-Comet.

    Primeiro usa agregação temporal para cobrir 24h/7d/30d de forma eficiente.
    Se o STH não tiver coleção agregada para aquele atributo, usa histórico bruto
    paginado/amostrado ao longo de toda a janela como fallback.
    """
    urn = device_id_to_urn(device_id)
    headers = _fiware_headers()

    now = datetime.now(timezone.utc)
    date_from = now - _period_delta(period)

    date_from_str = (
        date_from.isoformat(timespec="milliseconds").replace("+00:00", "Z")
    )
    date_to_str = now.isoformat(timespec="milliseconds").replace("+00:00", "Z")

    result = HistorySeries()
    aggregation_period = _aggregation_period(period)

    attributes = (
        (settings.sth_temperature_attribute, "temperature"),
        (settings.sth_humidity_attribute, "humidity"),
        (settings.sth_luminosity_attribute, "luminosity"),
    )

    async with httpx.AsyncClient(timeout=12.0) as client:
        for attribute, field in attributes:
            url = (
                f"{settings.sth_comet_url.rstrip('/')}"
                f"/STH/v1/contextEntities/"
                f"type/{settings.entity_type}/"
                f"id/{urn}/attributes/{attribute}"
            )

            try:
                aggregated_response = await client.get(
                    url,
                    headers=headers,
                    params={
                        "aggrMethod": "min,max,sum",
                        "aggrPeriod": aggregation_period,
                        "dateFrom": date_from_str,
                        "dateTo": date_to_str,
                    },
                )

                aggregated_points: list[HistoryPoint] = []

                if aggregated_response.status_code == 200:
                    aggregated_points = _parse_sth_aggregated_values(
                        aggregated_response.json(),
                        period,
                    )
                elif aggregated_response.status_code != 404:
                    aggregated_response.raise_for_status()

                if aggregated_points:
                    setattr(result, field, _sort_and_dedupe(aggregated_points))
                    continue

                raw_points = await _fetch_raw_sampled_history(
                    client=client,
                    url=url,
                    headers=headers,
                    period=period,
                    date_from=date_from_str,
                    date_to=date_to_str,
                )
                setattr(result, field, raw_points)

            except httpx.HTTPError as exc:
                raise RuntimeError(
                    f"STH-Comet inacessível para '{attribute}' "
                    f"de '{device_id}': {exc}"
                ) from exc

    return result


def calculate_wine_memory(
    device_id: str,
    history: HistorySeries,
    triggers: TriggerConfig,
) -> WineMemoryResponse:
    """Calcula o Passaporte Ambiental a partir do histórico real do STH."""
    incidents: list[EnvironmentalIncident] = []
    incident_counter = 1
    total_intervals = 0
    anomaly_intervals = 0
    exposure_seconds = 0

    last_incident_dt: datetime | None = None
    last_incident_text = "Nenhum"

    def point_datetime(point: HistoryPoint) -> datetime | None:
        return _parse_datetime(point.timestamp)

    def format_duration(seconds: int) -> str:
        seconds = max(seconds, 0)

        if seconds < 60:
            return f"{seconds}s"

        minutes = seconds // 60

        if minutes < 60:
            return f"{minutes} min"

        hours = minutes // 60
        remaining_minutes = minutes % 60
        return f"{hours}h {remaining_minutes}min"

    def estimated_step(points: list[HistoryPoint]) -> int:
        datetimes = [
            point_datetime(point)
            for point in points
            if point_datetime(point) is not None
        ]

        differences: list[int] = []

        for previous, current in zip(datetimes, datetimes[1:]):
            if previous is None or current is None:
                continue

            seconds = int((current - previous).total_seconds())
            if seconds > 0:
                differences.append(seconds)

        # O Wine Memory usa histórico de 30 dias, normalmente agregado por
        # hora. Se houver um buraco de telemetria, não devemos interpretar
        # várias horas sem dados como exposição contínua.
        if differences:
            return max(min(int(median(differences)), 3600), 1)

        return max(min(int(settings.monitoring_interval), 3600), 1)

    def classify_point(
        point: HistoryPoint,
        minimum: float,
        maximum: float,
    ) -> tuple[str | None, float]:
        minimum_value = (
            point.min_value
            if point.min_value is not None
            else point.value
        )
        maximum_value = (
            point.max_value
            if point.max_value is not None
            else point.value
        )

        low_deviation = max(minimum - minimum_value, 0.0)
        high_deviation = max(maximum_value - maximum, 0.0)

        if low_deviation <= 0 and high_deviation <= 0:
            return None, point.value

        if high_deviation >= low_deviation:
            return "high", maximum_value

        return "low", minimum_value

    def process_sensor(
        points: list[HistoryPoint],
        sensor_type: str,
        sensor_label: str,
        minimum: float,
        maximum: float,
        unit: str,
    ) -> None:
        nonlocal incident_counter
        nonlocal total_intervals
        nonlocal anomaly_intervals
        nonlocal exposure_seconds
        nonlocal last_incident_dt
        nonlocal last_incident_text

        ordered_points = _sort_and_dedupe(points)
        step_seconds = estimated_step(ordered_points)

        active_direction: str | None = None
        start_point: HistoryPoint | None = None
        last_bad_point: HistoryPoint | None = None
        peak_value: float | None = None
        bad_point_count = 0

        def deviation(value: float, direction: str) -> float:
            if direction == "low":
                return max(minimum - value, 0.0)
            return max(value - maximum, 0.0)

        def close_incident(
            end_point: HistoryPoint | None,
            still_active: bool,
        ) -> None:
            nonlocal incident_counter
            nonlocal exposure_seconds
            nonlocal active_direction
            nonlocal start_point
            nonlocal last_bad_point
            nonlocal peak_value
            nonlocal bad_point_count

            if (
                active_direction is None
                or start_point is None
                or last_bad_point is None
                or peak_value is None
            ):
                return

            start_dt = point_datetime(start_point)
            last_bad_dt = point_datetime(last_bad_point)
            end_dt = point_datetime(end_point) if end_point else None

            # Cada ponto histórico representa no máximo um intervalo de
            # `step_seconds`. Assim, lacunas sem telemetria não são somadas como
            # se o sensor tivesse permanecido em anomalia durante todo o buraco.
            duration_seconds = max(bad_point_count * step_seconds, step_seconds)

            if still_active:
                ended_at = "Em andamento"
            else:
                ended_at = end_point.time if end_point else last_bad_point.time

            exposure_seconds += duration_seconds

            direction_label = "alta" if active_direction == "high" else "baixa"
            threshold_symbol = ">" if active_direction == "high" else "<"
            threshold_value = maximum if active_direction == "high" else minimum

            incidents.append(
                EnvironmentalIncident(
                    id=incident_counter,
                    type=sensor_type,
                    direction=active_direction,
                    title=f"{sensor_label} {direction_label}",
                    startedAt=start_point.time,
                    endedAt=ended_at,
                    duration=format_duration(duration_seconds),
                    peakValue=f"{round(peak_value, 1)}{unit}",
                    description=(
                        f"{sensor_label} {direction_label}: "
                        f"pico {round(peak_value, 1)}{unit} "
                        f"{threshold_symbol} limite de "
                        f"{threshold_value}{unit}."
                    ),
                    active=still_active,
                )
            )

            incident_counter += 1
            active_direction = None
            start_point = None
            last_bad_point = None
            peak_value = None
            bad_point_count = 0

        for point in ordered_points:
            total_intervals += 1
            direction, candidate_peak = classify_point(
                point,
                minimum,
                maximum,
            )

            if direction is None:
                if active_direction is not None:
                    close_incident(point, still_active=False)
                continue

            anomaly_intervals += 1

            if active_direction is None:
                active_direction = direction
                start_point = point
                last_bad_point = point
                peak_value = candidate_peak
                bad_point_count = 1

                start_dt = point_datetime(point)
                if (
                    start_dt
                    and (
                        last_incident_dt is None
                        or start_dt > last_incident_dt
                    )
                ):
                    last_incident_dt = start_dt
                    last_incident_text = point.time

                continue

            if direction != active_direction:
                close_incident(point, still_active=False)

                active_direction = direction
                start_point = point
                last_bad_point = point
                peak_value = candidate_peak
                bad_point_count = 1

                start_dt = point_datetime(point)
                if (
                    start_dt
                    and (
                        last_incident_dt is None
                        or start_dt > last_incident_dt
                    )
                ):
                    last_incident_dt = start_dt
                    last_incident_text = point.time

                continue

            last_bad_point = point
            bad_point_count += 1

            if (
                peak_value is None
                or deviation(candidate_peak, direction)
                > deviation(peak_value, direction)
            ):
                peak_value = candidate_peak

        if active_direction is not None:
            close_incident(None, still_active=True)

    process_sensor(
        history.temperature,
        "temperature",
        "Temperatura",
        triggers.temperature.min,
        triggers.temperature.max,
        " °C",
    )
    process_sensor(
        history.humidity,
        "humidity",
        "Umidade",
        triggers.humidity.min,
        triggers.humidity.max,
        "%",
    )
    process_sensor(
        history.luminosity,
        "luminosity",
        "Luminosidade",
        triggers.luminosity.min,
        triggers.luminosity.max,
        "%",
    )

    stability = (
        100.0
        if total_intervals == 0
        else round(
            (1 - (anomaly_intervals / total_intervals)) * 100,
            1,
        )
    )

    incidents.sort(
        key=lambda incident: incident.id,
    )

    return WineMemoryResponse(
        device_id=device_id,
        totalIncidents=len(incidents),
        exposureTime=format_duration(exposure_seconds),
        lastIncident=last_incident_text,
        stability=stability,
        incidents=incidents,
    )
