from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator


class SensorRange(BaseModel):
    min: float
    max: float

    @model_validator(mode="after")
    def validate_order(self):
        if self.min >= self.max:
            raise ValueError("O limite mínimo deve ser menor que o máximo.")
        return self


class TriggerConfig(BaseModel):
    temperature: SensorRange
    humidity: SensorRange
    luminosity: SensorRange


class DeviceRegistration(BaseModel):
    device_id: str = Field(
        min_length=1,
        max_length=80,
        pattern="^[A-Za-z0-9_-]+$",
    )
    name: str = Field(min_length=1, max_length=120)
    location: str = Field(default="Adega principal", max_length=120)


class DeviceItem(BaseModel):
    id: str
    name: str
    location: str
    online: bool = False
    temperature: float = 0.0
    humidity: float = 0.0
    luminosity: float = 0.0


class CurrentReading(BaseModel):
    device_id: str
    entity_urn: str
    timestamp: str
    temperature: float
    humidity: float
    luminosity: float
    online: bool = True
    status: str = "Normal"
    alerts: dict[str, bool] = Field(default_factory=dict)
    raw: dict[str, Any] = Field(default_factory=dict)


class HistoryPoint(BaseModel):
    time: str
    value: float
    timestamp: str | None = None
    min_value: float | None = None
    max_value: float | None = None
    samples: int | None = None


class HistorySeries(BaseModel):
    temperature: list[HistoryPoint] = Field(default_factory=list)
    humidity: list[HistoryPoint] = Field(default_factory=list)
    luminosity: list[HistoryPoint] = Field(default_factory=list)


class HistoryResponse(BaseModel):
    device_id: str
    period: str
    history: HistorySeries
    source: str = "sth-comet"


class EnvironmentalIncident(BaseModel):
    id: int
    type: Literal["temperature", "humidity", "luminosity"]
    direction: Literal["high", "low"]
    title: str
    startedAt: str
    endedAt: str
    duration: str
    peakValue: str
    description: str
    active: bool = False


class WineMemoryResponse(BaseModel):
    device_id: str
    totalIncidents: int = 0
    exposureTime: str = "0 min"
    lastIncident: str = "Nenhum"
    stability: float | None = None
    incidents: list[EnvironmentalIncident] = Field(default_factory=list)
    sampleCount: int = 0
    source: Literal["recorded", "estimated"] = "estimated"


class AlertItem(BaseModel):
    id: int
    sensor: str
    message: str
    value: str
    time: str
    active: bool = True


class MonitoringStatus(BaseModel):
    device_id: str
    is_active: bool
    last_check: str | None = None
    active_alerts: dict[str, bool] = Field(default_factory=dict)


class CommandRequest(BaseModel):
    device_id: str = Field(min_length=1, max_length=80)
    command: Literal["alertTemp", "alertHum", "alertLum"]
    value: Literal["high", "low", "off"] = "off"
