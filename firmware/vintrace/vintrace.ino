#include <WiFi.h>
#include <PubSubClient.h>

#include <DHT.h>

#include <SPI.h>
#include <Adafruit_GFX.h>
#include <Adafruit_ST7735.h>

#include "secrets.h"

// =====================================================
// FIWARE / MQTT
// =====================================================

const char* DEVICE_ID = "vintrace001";

const char* TOPIC_TELEMETRY =
  "/ul/TEF/vintrace001/attrs";

const char* TOPIC_COMMAND =
  "/TEF/vintrace001/cmd";

const char* TOPIC_COMMAND_RESULT =
  "/ul/TEF/vintrace001/cmdexe";

// =====================================================
// PINOS
// =====================================================

#define DHT_PIN 4
#define DHT_TYPE DHT11

#define LDR_PIN 34

#define TFT_CS 21
#define TFT_DC 16
#define TFT_RST 17

#define LED_PIN 27
#define BUZZER_PIN 25

// =====================================================
// OBJETOS
// =====================================================

WiFiClient wifiClient;
PubSubClient mqttClient(wifiClient);

DHT dht(DHT_PIN, DHT_TYPE);

Adafruit_ST7735 tft =
  Adafruit_ST7735(TFT_CS, TFT_DC, TFT_RST);

// =====================================================
// CORES PERSONALIZADAS
// =====================================================

// Roxo/vinho
uint16_t COLOR_WINE = 0x780F;

// Laranja
uint16_t COLOR_ORANGE = 0xFD20;

// Fundo dos cards
uint16_t COLOR_CARD = 0x1082;

// Borda discreta
uint16_t COLOR_BORDER = 0x6B4D;

// Fundo escuro levemente azulado
uint16_t COLOR_BACKGROUND = 0x0841;

// =====================================================
// ALERTAS
// =====================================================

bool alertaTemperatura = false;
bool alertaUmidade = false;
bool alertaLuminosidade = false;

// -1 = abaixo do limite
//  0 = normal
//  1 = acima do limite
int modoTemperatura = 0;
int modoUmidade = 0;
int modoLuminosidade = 0;

bool ledLigado = false;

unsigned long ultimoPisca = 0;
unsigned long ultimoSom = 0;
unsigned long ultimaLeitura = 0;

int indiceSom = 0;

// =====================================================
// VALORES DOS SENSORES
// =====================================================

float temperatura = 0;
float umidade = 0;
int luminosidade = 0;

// =====================================================
// WIFI
// =====================================================

void conectarWiFi() {

  Serial.println();
  Serial.print("Conectando ao Wi-Fi: ");
  Serial.println(WIFI_SSID);

  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);

  while (WiFi.status() != WL_CONNECTED) {

    delay(500);
    Serial.print(".");
  }

  Serial.println();
  Serial.println("Wi-Fi conectado!");

  Serial.print("IP do ESP32: ");
  Serial.println(WiFi.localIP());
}

// =====================================================
// RESPOSTA DO COMANDO
// =====================================================

void responderComando(
  const String& comando,
  const String& resultado
) {

  String resposta =
    String(DEVICE_ID) +
    "@" +
    comando +
    "|" +
    resultado;

  mqttClient.publish(
    TOPIC_COMMAND_RESULT,
    resposta.c_str()
  );

  Serial.print("Resposta enviada: ");
  Serial.println(resposta);
}

// =====================================================
// RECEBER COMANDO DO FIWARE
// =====================================================

void callbackMQTT(
  char* topic,
  byte* payload,
  unsigned int length
) {

  String mensagem = "";

  for (unsigned int i = 0; i < length; i++) {
    mensagem += (char)payload[i];
  }

  Serial.println();
  Serial.println("------ COMANDO MQTT ------");

  Serial.print("Topico: ");
  Serial.println(topic);

  Serial.print("Mensagem: ");
  Serial.println(mensagem);

  int posicaoSeparador =
    mensagem.lastIndexOf('|');

  String valor = "";

  if (posicaoSeparador >= 0) {

    valor =
      mensagem.substring(
        posicaoSeparador + 1
      );
  }

  valor.trim();
  valor.toLowerCase();

  bool acima = valor == "on" || valor == "high";
  bool abaixo = valor == "low";
  bool desligar = valor == "off";

  // -----------------------------------------------------
  // TEMPERATURA
  // -----------------------------------------------------

  if (mensagem.indexOf("alertTemp") >= 0) {

    if (acima) {
      alertaTemperatura = true;
      modoTemperatura = 1;
    }

    else if (abaixo) {
      alertaTemperatura = true;
      modoTemperatura = -1;
    }

    else if (desligar) {
      alertaTemperatura = false;
      modoTemperatura = 0;
    }

    responderComando(
      "alertTemp",
      "OK"
    );
  }

  // -----------------------------------------------------
  // UMIDADE
  // -----------------------------------------------------

  else if (mensagem.indexOf("alertHum") >= 0) {

    if (acima) {
      alertaUmidade = true;
      modoUmidade = 1;
    }

    else if (abaixo) {
      alertaUmidade = true;
      modoUmidade = -1;
    }

    else if (desligar) {
      alertaUmidade = false;
      modoUmidade = 0;
    }

    responderComando(
      "alertHum",
      "OK"
    );
  }

  // -----------------------------------------------------
  // LUMINOSIDADE
  // -----------------------------------------------------

  else if (mensagem.indexOf("alertLum") >= 0) {

    if (acima) {
      alertaLuminosidade = true;
      modoLuminosidade = 1;
    }

    else if (abaixo) {
      alertaLuminosidade = true;
      modoLuminosidade = -1;
    }

    else if (desligar) {
      alertaLuminosidade = false;
      modoLuminosidade = 0;
    }

    responderComando(
      "alertLum",
      "OK"
    );
  }

  Serial.print("Temp alerta: ");
  Serial.print(alertaTemperatura);
  Serial.print(" | modo: ");
  Serial.println(modoTemperatura);

  Serial.print("Hum alerta: ");
  Serial.print(alertaUmidade);
  Serial.print(" | modo: ");
  Serial.println(modoUmidade);

  Serial.print("Lum alerta: ");
  Serial.print(alertaLuminosidade);
  Serial.print(" | modo: ");
  Serial.println(modoLuminosidade);

  Serial.println("--------------------------");

  atualizarTela();
}

// =====================================================
// CONECTAR MQTT
// =====================================================

void conectarMQTT() {

  while (!mqttClient.connected()) {

    Serial.print("Conectando ao MQTT...");

    String clientId = "vintrace001-";

    clientId += String(
      (uint32_t)ESP.getEfuseMac(),
      HEX
    );

    if (
      mqttClient.connect(
        clientId.c_str()
      )
    ) {

      Serial.println(" conectado!");

      mqttClient.subscribe(
        TOPIC_COMMAND
      );

      Serial.print("Inscrito em: ");
      Serial.println(TOPIC_COMMAND);
    }

    else {

      Serial.print(" falhou. Estado: ");
      Serial.println(mqttClient.state());

      delay(3000);
    }
  }
}

// =====================================================
// LEITURA DOS SENSORES
// =====================================================

void lerSensores() {

  float novaTemperatura =
    dht.readTemperature();

  float novaUmidade =
    dht.readHumidity();

  int ldrRaw =
    analogRead(LDR_PIN);

  // Na montagem física:
  // valor maior = mais escuro.
  // Portanto o percentual é invertido.

  luminosidade =
    map(
      ldrRaw,
      0,
      4095,
      100,
      0
    );

  luminosidade =
    constrain(
      luminosidade,
      0,
      100
    );

  if (!isnan(novaTemperatura)) {
    temperatura = novaTemperatura;
  }

  if (!isnan(novaUmidade)) {
    umidade = novaUmidade;
  }
}

// =====================================================
// ENVIAR TELEMETRIA
// =====================================================

void enviarTelemetria() {

  char payload[100];

  snprintf(
    payload,
    sizeof(payload),
    "t|%.1f|h|%.1f|l|%d",
    temperatura,
    umidade,
    luminosidade
  );

  bool publicado =
    mqttClient.publish(
      TOPIC_TELEMETRY,
      payload
    );

  Serial.println();
  Serial.println("------ TELEMETRIA ------");

  Serial.print("Temperatura: ");
  Serial.println(temperatura);

  Serial.print("Umidade: ");
  Serial.println(umidade);

  Serial.print("Luminosidade: ");
  Serial.println(luminosidade);

  Serial.print("Payload: ");
  Serial.println(payload);

  Serial.print("Topico: ");
  Serial.println(TOPIC_TELEMETRY);

  Serial.print("Publicado: ");
  Serial.println(
    publicado ? "SIM" : "NAO"
  );

  Serial.println("------------------------");
}

// =====================================================
// ELEMENTOS VISUAIS DA TFT
// =====================================================

void drawSensorRow(
  int y,
  const char* label,
  String value
) {

  tft.setTextSize(1);

  tft.setTextColor(ST77XX_WHITE);
  tft.setCursor(10, y);
  tft.print(label);

  tft.setTextColor(ST77XX_CYAN);
  tft.setCursor(48, y);
  tft.print(value);
}

// =====================================================
// ICONE: UVAS
// =====================================================

void drawGrapeIcon(int x, int y) {

  // Cabo
  tft.drawLine(
    x + 20,
    y + 2,
    x + 20,
    y + 9,
    ST77XX_GREEN
  );

  // Folhas
  tft.fillTriangle(
    x + 19,
    y + 7,
    x + 7,
    y + 4,
    x + 14,
    y + 14,
    ST77XX_GREEN
  );

  tft.fillTriangle(
    x + 21,
    y + 7,
    x + 34,
    y + 4,
    x + 27,
    y + 14,
    ST77XX_GREEN
  );

  // Uvas
  tft.fillCircle(
    x + 14,
    y + 18,
    6,
    COLOR_WINE
  );

  tft.fillCircle(
    x + 26,
    y + 18,
    6,
    COLOR_WINE
  );

  tft.fillCircle(
    x + 10,
    y + 29,
    6,
    COLOR_WINE
  );

  tft.fillCircle(
    x + 20,
    y + 29,
    6,
    COLOR_WINE
  );

  tft.fillCircle(
    x + 30,
    y + 29,
    6,
    COLOR_WINE
  );

  tft.fillCircle(
    x + 15,
    y + 40,
    6,
    COLOR_WINE
  );

  tft.fillCircle(
    x + 25,
    y + 40,
    6,
    COLOR_WINE
  );

  // Pequenos brilhos
  tft.drawPixel(
    x + 12,
    y + 16,
    ST77XX_WHITE
  );

  tft.drawPixel(
    x + 24,
    y + 16,
    ST77XX_WHITE
  );

  tft.drawPixel(
    x + 18,
    y + 27,
    ST77XX_WHITE
  );
}

// =====================================================
// ICONE: FOGO
// =====================================================

void drawFireIcon(int x, int y) {

  // chama externa vermelha
  tft.fillTriangle(
    x + 20, y + 0,
    x + 5,  y + 42,
    x + 35, y + 42,
    ST77XX_RED
  );

  tft.fillTriangle(
    x + 12, y + 17,
    x + 4,  y + 34,
    x + 16, y + 30,
    ST77XX_RED
  );

  tft.fillTriangle(
    x + 29, y + 10,
    x + 23, y + 28,
    x + 36, y + 22,
    ST77XX_RED
  );

  tft.fillCircle(
    x + 12, y + 35, 7, ST77XX_RED
  );

  tft.fillCircle(
    x + 20, y + 36, 9, ST77XX_RED
  );

  tft.fillCircle(
    x + 28, y + 34, 7, ST77XX_RED
  );

  // chama amarela
  tft.fillTriangle(
    x + 20, y + 10,
    x + 10, y + 40,
    x + 30, y + 40,
    ST77XX_YELLOW
  );

  tft.fillTriangle(
    x + 14, y + 22,
    x + 9,  y + 36,
    x + 18, y + 33,
    ST77XX_YELLOW
  );

  tft.fillTriangle(
    x + 27, y + 18,
    x + 21, y + 35,
    x + 31, y + 31,
    ST77XX_YELLOW
  );

  tft.fillCircle(
    x + 14, y + 35, 5, ST77XX_YELLOW
  );

  tft.fillCircle(
    x + 20, y + 34, 6, ST77XX_YELLOW
  );

  tft.fillCircle(
    x + 26, y + 34, 5, ST77XX_YELLOW
  );

  // chama interna branca
  tft.fillTriangle(
    x + 20, y + 18,
    x + 13, y + 40,
    x + 27, y + 40,
    ST77XX_WHITE
  );

  tft.fillCircle(
    x + 16, y + 35, 4, ST77XX_WHITE
  );

  tft.fillCircle(
    x + 20, y + 34, 5, ST77XX_WHITE
  );

  tft.fillCircle(
    x + 24, y + 35, 4, ST77XX_WHITE
  );
}

void drawSnowIcon(int x, int y) {

  uint16_t cor = ST77XX_CYAN;

  // floco
  tft.drawLine(x + 20, y + 5,  x + 20, y + 39, cor);
  tft.drawLine(x + 6,  y + 22, x + 34, y + 22, cor);

  tft.drawLine(x + 10, y + 12, x + 30, y + 32, cor);
  tft.drawLine(x + 30, y + 12, x + 10, y + 32, cor);

  // galhos
  tft.drawLine(x + 20, y + 5,  x + 16, y + 10, cor);
  tft.drawLine(x + 20, y + 5,  x + 24, y + 10, cor);

  tft.drawLine(x + 20, y + 39, x + 16, y + 34, cor);
  tft.drawLine(x + 20, y + 39, x + 24, y + 34, cor);

  tft.drawLine(x + 6,  y + 22, x + 11, y + 18, cor);
  tft.drawLine(x + 6,  y + 22, x + 11, y + 26, cor);

  tft.drawLine(x + 34, y + 22, x + 29, y + 18, cor);
  tft.drawLine(x + 34, y + 22, x + 29, y + 26, cor);

  tft.drawLine(x + 10, y + 12, x + 15, y + 12, cor);
  tft.drawLine(x + 10, y + 12, x + 10, y + 17, cor);

  tft.drawLine(x + 30, y + 12, x + 25, y + 12, cor);
  tft.drawLine(x + 30, y + 12, x + 30, y + 17, cor);

  tft.drawLine(x + 10, y + 32, x + 10, y + 27, cor);
  tft.drawLine(x + 10, y + 32, x + 15, y + 32, cor);

  tft.drawLine(x + 30, y + 32, x + 25, y + 32, cor);
  tft.drawLine(x + 30, y + 32, x + 30, y + 27, cor);
}

void drawDryIcon(int x, int y) {

  // contorno de gota seca
  tft.drawTriangle(
    x + 20, y + 2,
    x + 9,  y + 24,
    x + 31, y + 24,
    COLOR_ORANGE
  );

  tft.drawCircle(
    x + 20, y + 29,
    13,
    COLOR_ORANGE
  );

  tft.drawCircle(
    x + 20, y + 29,
    12,
    COLOR_ORANGE
  );

  // rachaduras
  tft.drawLine(
    x + 20, y + 15,
    x + 17, y + 20,
    ST77XX_YELLOW
  );

  tft.drawLine(
    x + 17, y + 20,
    x + 21, y + 24,
    ST77XX_YELLOW
  );

  tft.drawLine(
    x + 21, y + 24,
    x + 16, y + 30,
    ST77XX_YELLOW
  );

  tft.drawLine(
    x + 16, y + 30,
    x + 22, y + 35,
    ST77XX_YELLOW
  );

  tft.drawLine(
    x + 21, y + 24,
    x + 26, y + 20,
    ST77XX_YELLOW
  );

  tft.drawLine(
    x + 26, y + 20,
    x + 24, y + 14,
    ST77XX_YELLOW
  );
}

void drawMoonIcon(int x, int y) {

  // lua
  tft.fillCircle(
    x + 20,
    y + 22,
    12,
    ST77XX_WHITE
  );

  // recorte para virar lua crescente
  tft.fillCircle(
    x + 25,
    y + 18,
    12,
    COLOR_CARD
  );

  // estrelas
  tft.drawPixel(x + 8,  y + 10, ST77XX_YELLOW);
  tft.drawPixel(x + 9,  y + 10, ST77XX_YELLOW);
  tft.drawPixel(x + 8,  y + 11, ST77XX_YELLOW);
  tft.drawPixel(x + 9,  y + 11, ST77XX_YELLOW);

  tft.drawPixel(x + 30, y + 8, ST77XX_CYAN);
  tft.drawPixel(x + 31, y + 8, ST77XX_CYAN);
  tft.drawPixel(x + 30, y + 9, ST77XX_CYAN);
  tft.drawPixel(x + 31, y + 9, ST77XX_CYAN);

  tft.drawPixel(x + 32, y + 31, ST77XX_YELLOW);
  tft.drawPixel(x + 33, y + 31, ST77XX_YELLOW);
  tft.drawPixel(x + 32, y + 32, ST77XX_YELLOW);
  tft.drawPixel(x + 33, y + 32, ST77XX_YELLOW);
}

// =====================================================
// ICONE: GOTA
// =====================================================

void drawDropIcon(int x, int y) {

  tft.fillTriangle(
    x + 20,
    y + 1,
    x + 8,
    y + 24,
    x + 32,
    y + 24,
    ST77XX_BLUE
  );

  tft.fillCircle(
    x + 20,
    y + 28,
    14,
    ST77XX_BLUE
  );

  // Brilho
  tft.fillCircle(
    x + 15,
    y + 23,
    3,
    ST77XX_WHITE
  );

  tft.drawPixel(
    x + 13,
    y + 28,
    ST77XX_WHITE
  );
}

// =====================================================
// ICONE: SOL / LUMINOSIDADE
// =====================================================

void drawSunIcon(int x, int y) {

  // Sol
  tft.fillCircle(
    x + 20,
    y + 22,
    10,
    ST77XX_YELLOW
  );

  // Raios
  tft.drawLine(
    x + 20,
    y + 1,
    x + 20,
    y + 9,
    ST77XX_YELLOW
  );

  tft.drawLine(
    x + 20,
    y + 35,
    x + 20,
    y + 43,
    ST77XX_YELLOW
  );

  tft.drawLine(
    x + 1,
    y + 22,
    x + 9,
    y + 22,
    ST77XX_YELLOW
  );

  tft.drawLine(
    x + 31,
    y + 22,
    x + 39,
    y + 22,
    ST77XX_YELLOW
  );

  tft.drawLine(
    x + 6,
    y + 7,
    x + 12,
    y + 13,
    ST77XX_YELLOW
  );

  tft.drawLine(
    x + 28,
    y + 31,
    x + 34,
    y + 37,
    ST77XX_YELLOW
  );

  tft.drawLine(
    x + 6,
    y + 37,
    x + 12,
    y + 31,
    ST77XX_YELLOW
  );

  tft.drawLine(
    x + 28,
    y + 13,
    x + 34,
    y + 7,
    ST77XX_YELLOW
  );
}

// =====================================================
// ICONE: MULTIPLOS ALERTAS
// =====================================================

void drawWarningIcon(int x, int y) {

  tft.fillTriangle(
    x + 20,
    y + 2,
    x + 3,
    y + 39,
    x + 37,
    y + 39,
    ST77XX_RED
  );

  tft.fillRect(
    x + 18,
    y + 14,
    4,
    13,
    ST77XX_WHITE
  );

  tft.fillRect(
    x + 18,
    y + 31,
    4,
    4,
    ST77XX_WHITE
  );
}

// =====================================================
// TFT
// =====================================================

void atualizarTela() {

  bool algumAlerta =
    alertaTemperatura ||
    alertaUmidade ||
    alertaLuminosidade;

  int totalAlertas = 0;

  if (alertaTemperatura) {
    totalAlertas++;
  }

  if (alertaUmidade) {
    totalAlertas++;
  }

  if (alertaLuminosidade) {
    totalAlertas++;
  }

  String detalhe =
    "Safra protegida";

  uint16_t statusColor =
    ST77XX_GREEN;

  // =====================================================
  // DEFINE STATUS PARA ALERTA UNICO
  // =====================================================

  if (alertaTemperatura) {

    if (modoTemperatura > 0) {
      detalhe = "Calor excessivo";
      statusColor = ST77XX_RED;
    }

    else {
      detalhe = "Frio excessivo";
      statusColor = ST77XX_CYAN;
    }
  }

  else if (alertaUmidade) {

    if (modoUmidade > 0) {
      detalhe = "Umidade alta";
      statusColor = ST77XX_BLUE;
    }

    else {
      detalhe = "Ambiente seco";
      statusColor = COLOR_ORANGE;
    }
  }

  else if (alertaLuminosidade) {

    if (modoLuminosidade > 0) {
      detalhe = "Luz excessiva";
      statusColor = ST77XX_YELLOW;
    }

    else {
      detalhe = "Pouca luz";
      statusColor = ST77XX_CYAN;
    }
  }

  if (totalAlertas > 1) {
    statusColor = ST77XX_RED;
  }

  // =====================================================
  // FUNDO
  // =====================================================

  tft.fillScreen(
    ST77XX_BLACK
  );

  tft.setTextWrap(false);

  // =====================================================
  // CABECALHO
  // =====================================================

  tft.fillRoundRect(
    4,
    4,
    152,
    22,
    6,
    COLOR_WINE
  );

  tft.setTextSize(2);

  tft.setTextColor(
    ST77XX_WHITE
  );

  tft.setCursor(
    10,
    8
  );

  tft.print(
    "VinTrace"
  );

  // =====================================================
  // CARD DOS SENSORES
  // =====================================================

  tft.fillRoundRect(
    4,
    32,
    92,
    50,
    6,
    COLOR_CARD
  );

  tft.drawRoundRect(
    4,
    32,
    92,
    50,
    6,
    COLOR_BORDER
  );

  tft.setTextSize(1);

  tft.setTextColor(
    ST77XX_WHITE
  );

  tft.setCursor(
    10,
    37
  );

  tft.print(
    "AMBIENTE"
  );

  drawSensorRow(
    50,
    "Temp:",
    String(temperatura, 1) + " C"
  );

  drawSensorRow(
    61,
    "Umid:",
    String(umidade, 1) + " %"
  );

  drawSensorRow(
    72,
    "Luz:",
    String(luminosidade) + " %"
  );

  // =====================================================
  // CARD DO ICONE
  // =====================================================

  tft.fillRoundRect(
    102,
    32,
    54,
    50,
    6,
    COLOR_CARD
  );

  tft.drawRoundRect(
    102,
    32,
    54,
    50,
    6,
    COLOR_BORDER
  );

  // =====================================================
  // ICONE CONFORME STATUS
  // =====================================================

  if (totalAlertas > 1) {

    drawWarningIcon(
      109,
      36
    );
  }

  else if (alertaTemperatura) {

    if (modoTemperatura > 0) {
      drawFireIcon(
        109,
        36
      );
    }

    else {
      drawSnowIcon(
        109,
        36
      );
    }
  }

  else if (alertaUmidade) {

    if (modoUmidade > 0) {
      drawDropIcon(
        109,
        35
      );
    }

    else {
      drawDryIcon(
        109,
        35
      );
    }
  }

  else if (alertaLuminosidade) {

    if (modoLuminosidade > 0) {
      drawSunIcon(
        109,
        35
      );
    }

    else {
      drawMoonIcon(
        109,
        35
      );
    }
  }

  else {

    drawGrapeIcon(
      109,
      34
    );
  }

  // =====================================================
  // CARD INFERIOR
  // =====================================================

  tft.fillRoundRect(
    4,
    88,
    152,
    36,
    6,
    COLOR_BACKGROUND
  );

  tft.drawRoundRect(
    4,
    88,
    152,
    36,
    6,
    statusColor
  );

  // =====================================================
  // MULTIPLOS ALERTAS
  // =====================================================

  if (totalAlertas > 1) {

    tft.setTextSize(1);

    tft.setTextColor(
      ST77XX_RED
    );

    tft.setCursor(
      10,
      91
    );

    tft.print(
      "ALERTAS ATIVOS"
    );

    int linhaY = 99;

    // ---------------------------------------------------
    // TEMPERATURA
    // ---------------------------------------------------

    if (alertaTemperatura) {

      if (modoTemperatura > 0) {

        tft.setTextColor(
          ST77XX_RED
        );

        tft.setCursor(
          10,
          linhaY
        );

        tft.print(
          "Temperatura alta"
        );
      }

      else {

        tft.setTextColor(
          ST77XX_CYAN
        );

        tft.setCursor(
          10,
          linhaY
        );

        tft.print(
          "Temperatura baixa"
        );
      }

      linhaY += 8;
    }

    // ---------------------------------------------------
    // UMIDADE
    // ---------------------------------------------------

    if (alertaUmidade) {

      if (modoUmidade > 0) {

        tft.setTextColor(
          ST77XX_BLUE
        );

        tft.setCursor(
          10,
          linhaY
        );

        tft.print(
          "Umidade alta"
        );
      }

      else {

        tft.setTextColor(
          COLOR_ORANGE
        );

        tft.setCursor(
          10,
          linhaY
        );

        tft.print(
          "Umidade baixa"
        );
      }

      linhaY += 8;
    }

    // ---------------------------------------------------
    // LUMINOSIDADE
    // ---------------------------------------------------

    if (alertaLuminosidade) {

      if (modoLuminosidade > 0) {

        tft.setTextColor(
          ST77XX_YELLOW
        );

        tft.setCursor(
          10,
          linhaY
        );

        tft.print(
          "Luminosidade alta"
        );
      }

      else {

        tft.setTextColor(
          ST77XX_CYAN
        );

        tft.setCursor(
          10,
          linhaY
        );

        tft.print(
          "Luminosidade baixa"
        );
      }

      linhaY += 8;
    }

    return;
  }

  // =====================================================
  // ALERTA UNICO OU NORMAL
  // =====================================================

  tft.setTextSize(2);

  tft.setTextColor(
    statusColor
  );

  tft.setCursor(
    10,
    94
  );

  if (algumAlerta) {

    tft.print(
      "ALERTA"
    );
  }

  else {

    tft.print(
      "NORMAL"
    );
  }

  // =====================================================
  // DESCRICAO
  // =====================================================

  tft.setTextSize(1);

  tft.setTextColor(
    ST77XX_WHITE
  );

  tft.setCursor(
    10,
    114
  );

  tft.print(
    detalhe
  );
}

// =====================================================
// LED E BUZZER
// =====================================================

void controlarAlertas() {

  bool algumAlerta =
    alertaTemperatura ||
    alertaUmidade ||
    alertaLuminosidade;

  // -----------------------------------------------------
  // SEM ALERTA
  // -----------------------------------------------------

  if (!algumAlerta) {

    digitalWrite(
      LED_PIN,
      LOW
    );

    noTone(
      BUZZER_PIN
    );

    ledLigado = false;

    return;
  }

  // -----------------------------------------------------
  // LED PISCANDO
  // -----------------------------------------------------

  if (
    millis() - ultimoPisca >= 350
  ) {

    ultimoPisca =
      millis();

    ledLigado =
      !ledLigado;

    digitalWrite(
      LED_PIN,
      ledLigado
        ? HIGH
        : LOW
    );
  }

  // -----------------------------------------------------
  // BUZZER
  // -----------------------------------------------------

  if (
    millis() - ultimoSom >= 500
  ) {

    ultimoSom =
      millis();

    int frequencias[3];
    int quantidade = 0;

    // Temperatura
    if (alertaTemperatura) {

      frequencias[
        quantidade++
      ] = 700;
    }

    // Umidade
    if (alertaUmidade) {

      frequencias[
        quantidade++
      ] = 1100;
    }

    // Luminosidade
    if (alertaLuminosidade) {

      frequencias[
        quantidade++
      ] = 1600;
    }

    if (quantidade > 0) {

      if (
        indiceSom >= quantidade
      ) {

        indiceSom = 0;
      }

      tone(
        BUZZER_PIN,
        frequencias[indiceSom]
      );

      indiceSom++;
    }
  }
}

// =====================================================
// SETUP
// =====================================================

void setup() {

  Serial.begin(
    115200
  );

  delay(1000);

  // -----------------------------------------------------
  // PINOS
  // -----------------------------------------------------

  pinMode(
    LED_PIN,
    OUTPUT
  );

  pinMode(
    BUZZER_PIN,
    OUTPUT
  );

  pinMode(
    LDR_PIN,
    INPUT
  );

  digitalWrite(
    LED_PIN,
    LOW
  );

  noTone(
    BUZZER_PIN
  );

  // -----------------------------------------------------
  // DHT
  // -----------------------------------------------------

  dht.begin();

  // -----------------------------------------------------
  // TFT
  // -----------------------------------------------------

  SPI.begin(
    18,
    -1,
    23,
    21
  );

  tft.initR(
    INITR_BLACKTAB
  );

  // Tela em modo paisagem: 160 x 128
  tft.setRotation(
    1
  );

  tft.fillScreen(
    ST77XX_BLACK
  );

  // -----------------------------------------------------
  // SPLASH SCREEN
  // -----------------------------------------------------

  tft.fillRoundRect(
    10,
    18,
    140,
    88,
    10,
    COLOR_WINE
  );

  tft.setTextColor(
    ST77XX_WHITE
  );

  tft.setTextSize(
    2
  );

  tft.setCursor(
    32,
    35
  );

  tft.println(
    "VinTrace"
  );

  tft.setTextSize(
    1
  );

  tft.setCursor(
    33,
    61
  );

  tft.println(
    "Wine Guardian"
  );

  tft.setCursor(
    38,
    80
  );

  tft.println(
    "Conectando..."
  );

  // -----------------------------------------------------
  // WIFI
  // -----------------------------------------------------

  conectarWiFi();

  // -----------------------------------------------------
  // MQTT
  // -----------------------------------------------------

  mqttClient.setServer(
    MQTT_BROKER,
    MQTT_PORT
  );

  mqttClient.setCallback(
    callbackMQTT
  );

  conectarMQTT();

  // -----------------------------------------------------
  // PRIMEIRA LEITURA
  // -----------------------------------------------------

  lerSensores();

  atualizarTela();
}

// =====================================================
// LOOP
// =====================================================

void loop() {

  // -----------------------------------------------------
  // WIFI
  // -----------------------------------------------------

  if (
    WiFi.status()
    != WL_CONNECTED
  ) {

    conectarWiFi();
  }

  // -----------------------------------------------------
  // MQTT
  // -----------------------------------------------------

  if (
    !mqttClient.connected()
  ) {

    conectarMQTT();
  }

  mqttClient.loop();

  // -----------------------------------------------------
  // ALERTAS
  // -----------------------------------------------------

  controlarAlertas();

  // -----------------------------------------------------
  // TELEMETRIA A CADA 5 SEGUNDOS
  // -----------------------------------------------------

  if (
    millis() - ultimaLeitura
    >= 5000
  ) {

    ultimaLeitura =
      millis();

    lerSensores();

    enviarTelemetria();

    atualizarTela();
  }
}