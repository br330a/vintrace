# Roteiro de pitch — VinTrace

**Equipe:** Felipe Ilek, Bruno Gonçalves Minitti, Marcos Vinícius Tudisco, Michel Tatsuya Hanada, Nicolas Gomes de Almeida e Lucas Ferreira Rodrigues Silva.

## 1. Problema

A conservação de vinhos depende de condições ambientais estáveis. Variações de temperatura, umidade e luminosidade podem passar despercebidas sem monitoramento contínuo.

## 2. Solução

O VinTrace conecta sensores físicos a uma arquitetura FIWARE e a um dashboard web. O sistema acompanha o ambiente, guarda histórico, permite configurar limites e aciona alertas físicos remotamente.

## 3. Demonstração técnica

1. Mostrar o protótipo físico e identificar ESP32, DHT11, LDR, TFT, LED e buzzer. Se a carcaça estiver concluída até a banca, apresentá-la neste momento.
2. Abrir o dashboard e confirmar `vintrace001` online.
3. Mostrar temperatura, umidade e luminosidade atuais.
4. Mostrar os gráficos vindos do STH-Comet.
5. Alterar um trigger no dashboard para provocar uma anomalia controlada.
6. Mostrar o comando chegando ao ESP32: TFT, LED piscando e som correspondente.
7. Restaurar o trigger e mostrar a normalização.
8. Abrir o Wine Memory e explicar o Passaporte Ambiental.

## 4. Diferencial

O Wine Memory transforma o histórico ambiental em incidentes de exposição, mostrando sensor, direção, duração e pico. O TFT também diferencia alertas acima e abaixo da faixa e apresenta múltiplas anomalias simultâneas.

## 5. Encerramento

Mostrar o repositório, a arquitetura em camadas, o Wokwi público e os manuais. Finalizar reforçando que o fluxo demonstrado percorre o dashboard, backend, FIWARE e hardware físico.
