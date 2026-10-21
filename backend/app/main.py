from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, HTTPException, Query, status
from fastapi.middleware.cors import CORSMiddleware

from .config import settings
from .fiware import (
    calculate_wine_memory,
    check_fiware_health,
    delete_device_fiware,
    fetch_sth_history,
    get_current_reading,
    list_devices_fiware,
    register_device_fiware,
    send_fiware_command,
)
from .models import (
    CommandRequest,
    CurrentReading,
    DeviceRegistration,
    HistoryResponse,
    TriggerConfig,
    WineMemoryResponse,
)
from .monitor import monitor
from .triggers_store import (
    default_trigger_config,
    delete_device_triggers,
    get_device_triggers,
    save_device_triggers,
    triggers_are_persisted,
)


@asynccontextmanager
async def lifespan(_: FastAPI):
    monitor.start_loop()
    monitor.start_monitoring_device("vintrace001")
    yield
    monitor.stop_loop()


app = FastAPI(
    title="VinTrace API",
    version="1.1.0",
    description=(
        "API do VinTrace integrada ao FIWARE Orion, IoT Agent UltraLight "
        "e STH-Comet."
    ),
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/")
def root():
    return {
        "service": "VinTrace API",
        "status": "online",
        "docs": "/docs",
        "health": "/health",
        "devices": "/devices",
    }


@app.get("/health")
def health():
    return {
        "status": "ok",
        "service": "vintrace-api",
        "environment": settings.app_env,
        "fiware_service": settings.fiware_service,
        "fiware_service_path": settings.fiware_service_path,
        "trigger_storage": settings.trigger_storage,
    }


@app.get("/health/fiware")
async def health_fiware():
    return await check_fiware_health()


@app.get("/devices", response_model=dict[str, Any])
@app.get("/api/devices", response_model=dict[str, Any])
async def list_devices():
    """Lista somente dispositivos reais disponíveis no Orion."""
    try:
        devices = await list_devices_fiware()
    except Exception as exc:
        raise HTTPException(
            status_code=502,
            detail=f"Falha ao consultar dispositivos no FIWARE: {exc}",
        ) from exc

    return {
        "items": [device.model_dump() for device in devices],
        "total": len(devices),
        "source": "fiware",
    }


@app.post("/devices", status_code=status.HTTP_201_CREATED)
@app.post("/api/devices", status_code=status.HTTP_201_CREATED)
async def create_device(payload: DeviceRegistration):
    """Provisiona o dispositivo e inicializa seus triggers."""
    try:
        registration = await register_device_fiware(
            device_id=payload.device_id,
            name=payload.name,
            location=payload.location,
        )

        triggers = default_trigger_config()
        storage = await save_device_triggers(
            payload.device_id,
            triggers,
        )

    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=502,
            detail=f"Erro ao registrar no FIWARE: {exc}",
        ) from exc

    monitor.start_monitoring_device(payload.device_id)

    return {
        "id": payload.device_id,
        "name": payload.name,
        "location": payload.location,
        "fiware": registration,
        "triggers": triggers.model_dump(),
        "trigger_storage": storage,
    }


@app.delete("/devices/{device_id}")
@app.delete("/api/devices/{device_id}")
async def remove_device(device_id: str):
    """Desliga alertas, remove o dispositivo do FIWARE e limpa o cache local."""
    await monitor.stop_monitoring_device(device_id)

    try:
        await delete_device_fiware(device_id)
    except Exception as exc:
        raise HTTPException(
            status_code=502,
            detail=f"Falha ao excluir dispositivo do FIWARE: {exc}",
        ) from exc

    delete_device_triggers(device_id)

    return {
        "device_id": device_id,
        "deleted": True,
    }


@app.get("/devices/{device_id}/current", response_model=CurrentReading)
@app.get("/api/devices/{device_id}/current", response_model=CurrentReading)
async def current_reading(device_id: str):
    try:
        return await get_current_reading(device_id)
    except Exception as exc:
        raise HTTPException(
            status_code=502,
            detail=f"Falha ao consultar Orion: {exc}",
        ) from exc


@app.get("/devices/{device_id}/history", response_model=HistoryResponse)
@app.get("/api/devices/{device_id}/history", response_model=HistoryResponse)
async def device_history(
    device_id: str,
    period: str = Query(default="24h", pattern="^(24h|7d|30d)$"),
):
    try:
        series = await fetch_sth_history(
            device_id=device_id,
            period=period,
        )

        return HistoryResponse(
            device_id=device_id,
            period=period,
            history=series,
            source="sth-comet",
        )
    except Exception as exc:
        raise HTTPException(
            status_code=503,
            detail=f"Falha ao consultar STH-Comet: {exc}",
        ) from exc


@app.get("/devices/{device_id}/triggers")
@app.get("/api/devices/{device_id}/triggers")
@app.get("/api/triggers/{device_id}")
async def get_triggers_endpoint(device_id: str):
    triggers = await get_device_triggers(device_id)
    persisted = await triggers_are_persisted(device_id)

    return {
        "device_id": device_id,
        "triggers": triggers.model_dump(),
        "storage": settings.trigger_storage,
        "persisted": persisted,
    }


@app.put("/devices/{device_id}/triggers")
@app.put("/api/devices/{device_id}/triggers")
@app.put("/api/triggers/{device_id}")
async def update_triggers_endpoint(
    device_id: str,
    payload: TriggerConfig,
):
    try:
        storage = await save_device_triggers(device_id, payload)
    except Exception as exc:
        raise HTTPException(
            status_code=502,
            detail=f"Falha ao persistir triggers: {exc}",
        ) from exc

    return {
        "device_id": device_id,
        "triggers": payload.model_dump(),
        "storage": storage,
        "persisted": True,
        "message": "Triggers salvos e aplicados ao monitoramento.",
    }


@app.get(
    "/devices/{device_id}/wine-memory",
    response_model=WineMemoryResponse,
)
@app.get(
    "/api/devices/{device_id}/wine-memory",
    response_model=WineMemoryResponse,
)
async def wine_memory_endpoint(device_id: str):
    triggers = await get_device_triggers(device_id)

    try:
        series = await fetch_sth_history(
            device_id=device_id,
            period="30d",
        )

        return calculate_wine_memory(
            device_id,
            series,
            triggers,
        )
    except Exception as exc:
        raise HTTPException(
            status_code=503,
            detail=f"Falha ao gerar Wine Memory: {exc}",
        ) from exc


@app.get("/devices/{device_id}/alerts")
@app.get("/api/devices/{device_id}/alerts")
def get_alerts_endpoint(device_id: str):
    alerts = monitor.get_recent_alerts(device_id)

    return {
        "device_id": device_id,
        "alerts": [alert.model_dump() for alert in alerts],
    }


@app.post("/devices/{device_id}/monitoring/start")
@app.post("/api/devices/{device_id}/monitoring/start")
def start_monitoring_endpoint(device_id: str):
    monitor.start_monitoring_device(device_id)
    return {"device_id": device_id, "monitoring": True}


@app.post("/devices/{device_id}/monitoring/stop")
@app.post("/api/devices/{device_id}/monitoring/stop")
async def stop_monitoring_endpoint(device_id: str):
    await monitor.stop_monitoring_device(device_id)
    return {"device_id": device_id, "monitoring": False}


@app.get("/devices/{device_id}/monitoring")
@app.get("/api/devices/{device_id}/monitoring")
def get_monitoring_status_endpoint(device_id: str):
    return monitor.get_status(device_id)


@app.post("/commands")
@app.post("/api/commands")
async def manual_command(payload: CommandRequest):
    try:
        return await send_fiware_command(
            device_id=payload.device_id,
            command=payload.command,
            value=payload.value,
        )
    except Exception as exc:
        raise HTTPException(
            status_code=502,
            detail=f"Falha ao emitir comando FIWARE: {exc}",
        ) from exc
