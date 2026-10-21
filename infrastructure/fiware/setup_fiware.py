#!/usr/bin/env python3
"""Script de provisionamento e validação do ambiente FIWARE para o VinTrace.
Configura Service Group no IoT Agent UltraLight e Subscription no Orion para o STH-Comet.
"""
import os
import sys
import httpx

ORION_URL = os.getenv("FIWARE_BASE_URL", "http://localhost:1026")
IOT_AGENT_URL = os.getenv("IOT_AGENT_URL", "http://localhost:4041")
STH_COMET_URL = os.getenv("STH_COMET_URL", "http://localhost:8666")
FIWARE_SERVICE = os.getenv("FIWARE_SERVICE", "smart")
FIWARE_SERVICE_PATH = os.getenv("FIWARE_SERVICE_PATH", "/")
API_KEY = os.getenv("FIWARE_API_KEY", "TEF")
ENTITY_TYPE = os.getenv("ENTITY_TYPE", "VinTrace")

HEADERS = {
    "Fiware-Service": FIWARE_SERVICE,
    "Fiware-ServicePath": FIWARE_SERVICE_PATH,
    "Content-Type": "application/json",
    "Accept": "application/json",
}


def device_id_to_urn(device_id: str) -> str:
    if device_id.startswith("urn:ngsi-ld:"):
        return device_id

    if device_id.lower().startswith("vintrace"):
        suffix = device_id[len("vintrace"):].lstrip("_-")
        if suffix:
            return f"urn:ngsi-ld:{ENTITY_TYPE}:{suffix}"

    return f"urn:ngsi-ld:{ENTITY_TYPE}:{device_id}"


def check_services():
    print("--- 1. Verificando conectividade com o stack FIWARE ---")
    for name, url in [("Orion Context Broker", f"{ORION_URL}/version"),
                      ("IoT Agent UltraLight", f"{IOT_AGENT_URL}/iot/about"),
                      ("STH-Comet", f"{STH_COMET_URL}/version")]:
        try:
            r = httpx.get(url, timeout=4.0)
            status = "ONLINE" if r.status_code == 200 else f"HTTP {r.status_code}"
            print(f"  [+] {name} ({url}): {status}")
        except Exception as exc:
            print(f"  [-] {name} ({url}): OFFLINE ({exc})")


def provision_service_group():
    print("\n--- 2. Provisionando Service Group no IoT Agent ---")
    url = f"{IOT_AGENT_URL.rstrip('/')}/iot/services"
    payload = {
        "services": [
            {
                "apikey": API_KEY,
                "cbroker": "http://orion:1026",
                "entity_type": ENTITY_TYPE,
                "resource": "/iot/d",
            }
        ]
    }
    try:
        r = httpx.post(url, headers=HEADERS, json=payload, timeout=6.0)
        if r.status_code in (201, 200):
            print("  [OK] Service Group criado com sucesso!")
        elif r.status_code == 409:
            print("  [INFO] Service Group já provisionado.")
        else:
            print(f"  [WARN] Resposta do IoT Agent: {r.status_code} - {r.text}")
    except Exception as exc:
        print(f"  [ERRO] Falha ao conectar ao IoT Agent: {exc}")


def provision_sth_subscription():
    print("\n--- 3. Provisionando Subscription no Orion Context Broker para STH-Comet ---")
    url = f"{ORION_URL.rstrip('/')}/v2/subscriptions"
    payload = {
        "description": "VinTrace STH-Comet Time Series Subscription",
        "subject": {
            "entities": [
                {
                    "idPattern": ".*",
                    "type": ENTITY_TYPE,
                }
            ],
            "condition": {
                "attrs": ["temperature", "humidity", "luminosity"]
            },
        },
        "notification": {
            "http": {
                "url": "http://sth-comet:8666/notify"
            },
            "attrs": ["temperature", "humidity", "luminosity"],
            "attrsFormat": "legacy",
        },
        "throttling": 1,
    }
    try:
        r = httpx.post(url, headers=HEADERS, json=payload, timeout=6.0)
        if r.status_code in (201, 200):
            print("  [OK] Subscription criada no Orion com sucesso!")
        else:
            print(f"  [INFO] Resposta do Orion: {r.status_code} - {r.text}")
    except Exception as exc:
        print(f"  [ERRO] Falha ao conectar ao Orion: {exc}")


def provision_default_device(device_id="vintrace001", name="Adega principal", location="Laboratório"):
    print(f"\n--- 4. Provisionando Dispositivo de Teste '{device_id}' ---")
    url = f"{IOT_AGENT_URL.rstrip('/')}/iot/devices"
    payload = {
        "devices": [
            {
                "device_id": device_id,
                "entity_name": device_id_to_urn(device_id),
                "entity_type": ENTITY_TYPE,
                "protocol": "PDI-IoTA-UltraLight",
                "transport": "MQTT",
                "apikey": API_KEY,
                "timezone": "America/Sao_Paulo",
                "attributes": [
                    {"object_id": "t", "name": "temperature", "type": "Number"},
                    {"object_id": "h", "name": "humidity", "type": "Number"},
                    {"object_id": "l", "name": "luminosity", "type": "Number"},
                ],
                "commands": [
                    {"name": "alertTemp", "type": "command"},
                    {"name": "alertHum", "type": "command"},
                    {"name": "alertLum", "type": "command"},
                ],
                "static_attributes": [
                    {"name": "name", "type": "Text", "value": name},
                    {"name": "location", "type": "Text", "value": location},
                    {"name": "deviceId", "type": "Text", "value": device_id},
                ],
            }
        ]
    }
    try:
        r = httpx.post(url, headers=HEADERS, json=payload, timeout=6.0)
        if r.status_code in (201, 200):
            print(f"  [OK] Dispositivo '{device_id}' registrado com sucesso no IoT Agent!")
        elif r.status_code == 409:
            print(f"  [INFO] Dispositivo '{device_id}' já registrado no IoT Agent.")
        else:
            print(f"  [WARN] Resposta do IoT Agent: {r.status_code} - {r.text}")
    except Exception as exc:
        print(f"  [ERRO] Falha ao conectar ao IoT Agent: {exc}")


if __name__ == "__main__":
    check_services()
    provision_service_group()
    provision_sth_subscription()
    provision_default_device()
    print("\n[OK] Setup FIWARE finalizado.")
