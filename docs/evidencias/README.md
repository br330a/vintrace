# Evidências de funcionamento

Esta pasta reúne evidências visuais da versão final do VinTrace utilizada nos testes do Check Point 5.

As imagens demonstram a integração entre dashboard web, backend, FIWARE, STH-Comet, ESP32 físico e simulação Wokwi.

## Evidências

### Dashboard online

Arquivo: `imagens/dashboard-online.png`

Demonstra o dashboard principal do VinTrace em funcionamento e conectado à infraestrutura utilizada pelo projeto.

### Dispositivo online

Arquivo: `imagens/dispositivos-online.png`

Demonstra o dispositivo `vintrace001` cadastrado e identificado como online, com dados provenientes do ESP32 físico.

### Histórico de temperatura

Arquivo: `imagens/graficos-temp.png`

Demonstra a visualização dos dados históricos de temperatura obtidos por meio do STH-Comet.

### Histórico de luminosidade

Arquivo: `imagens/graficos-luz.png`

Demonstra a visualização dos dados históricos de luminosidade armazenados pelo STH-Comet.

### Configuração dos triggers

Arquivo: `imagens/triggers.png`

Demonstra a configuração das faixas de temperatura, umidade e luminosidade através do front-end.

Os limites são utilizados pelo backend para identificar anomalias e enviar comandos remotamente ao ESP32 através da infraestrutura FIWARE.

### Alerta no dashboard

Arquivo: `imagens/alerta-dashboard.png`

Demonstra uma condição fora dos limites configurados e a identificação do alerta pelo sistema.

No hardware físico, a condição de alerta também provoca:

- acionamento remoto do LED azul;
- LED piscando enquanto existir uma anomalia;
- sinal sonoro específico para o sensor;
- indicação da anomalia no display TFT.

Quando as condições retornam aos limites configurados, o alerta é encerrado remotamente.

### Wine Memory

Arquivo: `imagens/wine-memory.png`

Demonstra o Wine Memory, diferencial do VinTrace responsável por analisar o histórico ambiental do dispositivo.

A funcionalidade identifica exposições fora dos limites configurados e apresenta informações como:

- quantidade de incidentes;
- tipo de sensor;
- direção da anomalia (`high` ou `low`);
- duração da exposição;
- valores de pico;
- estabilidade ambiental.

### Simulação Wokwi

Arquivo: `imagens/wokwi.png`

Demonstra a simulação do projeto utilizando:

- ESP32;
- DHT22;
- LDR;
- LED azul;
- buzzer.

A simulação foi testada com anomalias de temperatura, umidade e luminosidade, utilizando sinais sonoros diferentes para cada variável.

Projeto público:

https://wokwi.com/projects/478447086402895873

## Validação realizada

Além das evidências visuais, foram validados:

- leitura física de temperatura e umidade com DHT11;
- leitura física de luminosidade com LDR;
- telemetria ESP32 → MQTT → IoT Agent → Orion;
- armazenamento histórico no STH-Comet;
- consulta dos períodos de 24 horas, 7 dias e 30 dias;
- cadastro e exclusão de IoT Devices;
- configuração de triggers pelo dashboard;
- persistência dos triggers no Orion;
- alertas de temperatura alta e baixa;
- alertas de umidade alta e baixa;
- alertas de luminosidade alta e baixa;
- múltiplas anomalias simultâneas;
- LED azul piscando enquanto há alerta;
- buzzer com frequências distintas;
- display TFT indicando estado normal e diferentes tipos de alerta;
- normalização remota dos alertas;
- Wine Memory;
- funcionamento do dashboard em produção.