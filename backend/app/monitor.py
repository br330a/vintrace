"""Monitor de anomalias do VinTrace.

Compara periodicamente as leituras atuais do Orion com os triggers
persistidos e envia comandos remotos pelo FIWARE.

Estados enviados ao ESP32:
- high: acima do limite máximo
- low: abaixo do limite mínimo
- off: dentro da faixa normal
"""

import asyncio
from datetime import datetime, timezone
import logging
from zoneinfo import ZoneInfo

from .config import settings
from .fiware import get_current_reading, send_fiware_command
from .models import AlertItem, MonitoringStatus
from .triggers_store import get_device_triggers
from .wine_memory_events import record_transition


logger = logging.getLogger("vintrace.monitor")

BR_TZ = ZoneInfo("America/Sao_Paulo")

ALERT_OFF = "off"
ALERT_LOW = "low"
ALERT_HIGH = "high"


class AnomalyMonitor:
    def __init__(self):
        # device_id -> monitoramento ativo
        self.active_devices: dict[str, bool] = {}

        # device_id -> estado atual de cada alerta
        # None força uma sincronização inicial com o ESP32.
        self.device_alert_states: dict[
            str,
            dict[str, str | None],
        ] = {}

        # Histórico recente de alertas
        self.device_alerts_history: dict[
            str,
            list[AlertItem],
        ] = {}

        self.last_check: dict[str, str] = {}

        self._task: asyncio.Task | None = None
        self._running = False
        self._alert_id_counter = 1

    def _default_states(
        self,
    ) -> dict[str, str | None]:
        return {
            "alertTemp": None,
            "alertHum": None,
            "alertLum": None,
        }

    def _desired_state(
        self,
        value: float,
        minimum: float,
        maximum: float,
    ) -> str:
        if value < minimum:
            return ALERT_LOW

        if value > maximum:
            return ALERT_HIGH

        return ALERT_OFF

    def start_loop(self):
        if not self._running:
            self._running = True
            self._task = asyncio.create_task(
                self._monitor_loop()
            )

    def stop_loop(self):
        self._running = False

        if self._task:
            self._task.cancel()

    def start_monitoring_device(
        self,
        device_id: str,
    ) -> None:
        self.active_devices[device_id] = True

        # Força uma nova sincronização.
        # Isso é importante caso o ESP32 tenha sido reiniciado.
        self.device_alert_states[device_id] = (
            self._default_states()
        )

        if (
            device_id
            not in self.device_alerts_history
        ):
            self.device_alerts_history[
                device_id
            ] = []

        logger.info(
            "Monitoramento iniciado para o dispositivo '%s'.",
            device_id,
        )

    async def stop_monitoring_device(
        self,
        device_id: str,
    ) -> None:
        self.active_devices[device_id] = False

        current_states = (
            self.device_alert_states.get(
                device_id,
                self._default_states(),
            )
        )

        for command_name in (
            "alertTemp",
            "alertHum",
            "alertLum",
        ):
            state = current_states.get(
                command_name
            )

            if state != ALERT_OFF:
                try:
                    await send_fiware_command(
                        device_id,
                        command_name,
                        ALERT_OFF,
                    )
                except Exception as exc:
                    logger.warning(
                        "Erro ao desligar %s: %s",
                        command_name,
                        exc,
                    )

            current_states[
                command_name
            ] = ALERT_OFF

        logger.info(
            "Monitoramento parado para o dispositivo '%s'.",
            device_id,
        )

    def get_status(
        self,
        device_id: str,
    ) -> MonitoringStatus:
        states = self.device_alert_states.get(
            device_id,
            self._default_states(),
        )

        return MonitoringStatus(
            device_id=device_id,
            is_active=self.active_devices.get(
                device_id,
                False,
            ),
            last_check=self.last_check.get(
                device_id
            ),
            active_alerts={
                "alertTemp":
                    states.get("alertTemp")
                    not in (None, ALERT_OFF),

                "alertHum":
                    states.get("alertHum")
                    not in (None, ALERT_OFF),

                "alertLum":
                    states.get("alertLum")
                    not in (None, ALERT_OFF),
            },
        )

    def get_recent_alerts(
        self,
        device_id: str,
    ) -> list[AlertItem]:
        history = (
            self.device_alerts_history.get(
                device_id,
                [],
            )
        )

        return list(
            reversed(history)
        )[:10]

    async def _monitor_loop(self):
        while self._running:
            try:
                for (
                    device_id,
                    is_active,
                ) in list(
                    self.active_devices.items()
                ):
                    if is_active:
                        await self._evaluate_device(
                            device_id
                        )

            except Exception as exc:
                logger.error(
                    "Erro no ciclo de monitoramento: %s",
                    exc,
                )

            await asyncio.sleep(
                settings.monitoring_interval
            )

    async def _evaluate_device(
        self,
        device_id: str,
    ):
        self.last_check[
            device_id
        ] = datetime.now(
            timezone.utc
        ).isoformat()

        try:
            current = (
                await get_current_reading(
                    device_id
                )
            )
        except Exception as exc:
            logger.warning(
                "Falha ao obter leitura de %s: %s",
                device_id,
                exc,
            )
            return

        triggers = await get_device_triggers(
            device_id
        )

        current_state = (
            self.device_alert_states.setdefault(
                device_id,
                self._default_states(),
            )
        )

        now_formatted = datetime.now(
            BR_TZ
        ).strftime(
            "%d/%m, %H:%M"
        )

        await self._evaluate_sensor(
            device_id=device_id,
            command_name="alertTemp",
            sensor_name="Temperatura",
            value=current.temperature,
            minimum=triggers.temperature.min,
            maximum=triggers.temperature.max,
            unit="°C",
            current_state=current_state,
            now_formatted=now_formatted,
        )

        await self._evaluate_sensor(
            device_id=device_id,
            command_name="alertHum",
            sensor_name="Umidade",
            value=current.humidity,
            minimum=triggers.humidity.min,
            maximum=triggers.humidity.max,
            unit="%",
            current_state=current_state,
            now_formatted=now_formatted,
        )

        await self._evaluate_sensor(
            device_id=device_id,
            command_name="alertLum",
            sensor_name="Luminosidade",
            value=current.luminosity,
            minimum=triggers.luminosity.min,
            maximum=triggers.luminosity.max,
            unit="%",
            current_state=current_state,
            now_formatted=now_formatted,
        )

    async def _evaluate_sensor(
        self,
        device_id: str,
        command_name: str,
        sensor_name: str,
        value: float,
        minimum: float,
        maximum: float,
        unit: str,
        current_state: dict[
            str,
            str | None,
        ],
        now_formatted: str,
    ):
        desired_state = (
            self._desired_state(
                value,
                minimum,
                maximum,
            )
        )

        previous_state = (
            current_state.get(
                command_name
            )
        )

        if (
            desired_state
            == previous_state
        ):
            return

        try:
            await send_fiware_command(
                device_id,
                command_name,
                desired_state,
            )

            current_state[
                command_name
            ] = desired_state

            # Registro persistente da ocorrência com o trigger vigente.
            # Se o Orion não puder salvar o registro, o alerta físico
            # continua funcionando; a falha fica visível nos logs.
            try:
                await record_transition(
                    device_id=device_id,
                    command=command_name,
                    state=desired_state,
                    value=value,
                    limit=maximum if desired_state == ALERT_HIGH else minimum,
                )
            except Exception as exc:
                logger.warning(
                    "Não foi possível persistir ocorrência do Wine Memory (%s): %s",
                    device_id, exc,
                )

            # Sincronização inicial normal:
            # manda OFF para o ESP32, mas não cria
            # um falso evento de normalização.
            if (
                previous_state is None
                and desired_state
                == ALERT_OFF
            ):
                return

            if (
                desired_state
                == ALERT_HIGH
            ):
                message = (
                    f"{sensor_name} acima do limite "
                    f"({value}{unit} > "
                    f"{maximum}{unit})"
                )

                self._record_alert(
                    device_id,
                    sensor_name,
                    message,
                    f"{value}{unit}",
                    now_formatted,
                    active=True,
                )

            elif (
                desired_state
                == ALERT_LOW
            ):
                message = (
                    f"{sensor_name} abaixo do limite "
                    f"({value}{unit} < "
                    f"{minimum}{unit})"
                )

                self._record_alert(
                    device_id,
                    sensor_name,
                    message,
                    f"{value}{unit}",
                    now_formatted,
                    active=True,
                )

            else:
                self._record_alert(
                    device_id,
                    sensor_name,
                    f"{sensor_name} normalizada",
                    f"{value}{unit}",
                    now_formatted,
                    active=False,
                )

        except Exception as exc:
            logger.error(
                "Falha ao enviar %s=%s: %s",
                command_name,
                desired_state,
                exc,
            )

    def _record_alert(
        self,
        device_id: str,
        sensor: str,
        message: str,
        value: str,
        time: str,
        active: bool = True,
    ):
        item = AlertItem(
            id=self._alert_id_counter,
            sensor=sensor,
            message=message,
            value=value,
            time=time,
            active=active,
        )

        self._alert_id_counter += 1

        history = (
            self.device_alerts_history.setdefault(
                device_id,
                [],
            )
        )

        history.append(item)

        if len(history) > 50:
            history.pop(0)


monitor = AnomalyMonitor()