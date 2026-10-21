# Esquema elétrico — VinTrace

Pinagem utilizada no protótipo físico final.

| Componente | ESP32 | Observação |
|---|---:|---|
| DHT11 DATA | GPIO 4 | sensor físico de temperatura/umidade |
| LDR / divisor | GPIO 34 | entrada ADC1 |
| TFT SCK | GPIO 18 | SPI |
| TFT MOSI | GPIO 23 | SPI |
| TFT CS | GPIO 21 | chip select |
| TFT DC | GPIO 16 | data/command |
| TFT RST | GPIO 17 | reset |
| LED azul | GPIO 27 | usar resistor limitador |
| Buzzer passivo | GPIO 25 | tons por frequência |

## Alimentação

- utilizar GND comum entre os componentes;
- respeitar a tensão suportada por cada módulo;
- desligar o circuito antes de alterar conexões;
- não ligar LED externo sem resistor apropriado.

## LDR

O LDR é usado em divisor resistivo. O firmware final mapeia o ADC de modo invertido para que a porcentagem exibida corresponda ao comportamento observado no protótipo:

```cpp
map(ldrRaw, 0, 4095, 100, 0)
```

## Montagem física

A carcaça deve manter:

- DHT11 ventilado;
- LDR exposto à luz ambiente;
- saída sonora para o buzzer;
- LED visível;
- janela para o TFT;
- acesso ao USB e ao botão EN/RESET;
- fixação que impeça curto ou movimento das placas.

## Encapsulamento

O encapsulamento em formato de garrafa continua como pendência física do projeto. O principal impasse é definir uma solução de abertura/fechamento que permita instalar e manter ESP32, TFT, sensores, buzzer e fiação sem comprometer ventilação, leitura de luz e acesso ao USB.

Antes da impressão final, ainda devem ser definidos:

- mecanismo de abertura e fechamento;
- janela e fixação do TFT;
- ventilação do DHT11;
- exposição do LDR à luz ambiente;
- saída sonora do buzzer;
- visibilidade do LED;
- acesso ao USB e ao botão EN/RESET;
- suportes internos para evitar movimento e curto-circuito.
