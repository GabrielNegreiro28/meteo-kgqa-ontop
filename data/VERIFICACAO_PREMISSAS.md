# Verificação das premissas da base meteorológica

Data: 25/11/2026. As premissas que `DICIONARIO_DADOS.md` marcava como hipótese (H) foram testadas nos próprios dados e, para o tempo, contra
uma fonte externa com relógio conhecido. Nenhuma dependeu de resposta do professor.

Scripts e resultados (todos só leem o DuckDB):
- `verificar_fuso_metar.py` → `fuso_metar_resultado.json`: temperatura bruta contra METAR (UTC) do Iowa Environmental Mesonet, amostras em `metar_amostra/`;
- `verificar_premissas.py` → `premissas_resultado.json`: ciclo diário, horário de verão, unidades, boletins fora da hora cheia, consistência;
- `conferir_base_limpa_metar.py` → `conferencia_base_limpa_metar.json`: a base limpa corrigida contra os mesmos METAR;
- `efeito_correcao_fuso.py` → `efeito_correcao_fuso.json`: o que a correção mudou na base limpa.

## 1. Tempo: a premissa estava errada

A ingestão tratava `hora_observacao` como UTC−3 fixo em todas as estações e em todo o período. O relógio dos dados é outro, e muda:

| Período | Relógio de `hora_observacao` | Evidência |
|---|---|---|
| até 15/04/2021 | hora legal padrão da estação, sem horário de verão: UTC−2 (Fernando de Noronha), UTC−3, UTC−4 (AM, RR, RO, MT, MS), UTC−5 (AC e oeste do AM) | temperatura igual ao METAR em 94% a 100% das horas no deslocamento da hora legal, em 13 estações dos cinco fusos; São Paulo em janeiro de 2018 bate em UTC−3, não em UTC−2 |
| 16 a 30/04/2021 | quase sem dados fora da nuvem (376 linhas, relógio incerto: quarentena); a nuvem já está em UTC | ciclo diário dos cúmulos salta em 16/04 |
| 19/04/2021 | lote tardio no relógio antigo | METAR e ciclo dos cúmulos |
| desde 01/05/2021 | UTC, em todas as estações | temperatura igual ao METAR em 98% a 99% das horas com deslocamento zero |

Testes indiretos, antes do METAR: o ciclo diário não muda com o horário de verão (diferença das diferenças de 0,03 h entre estados com e sem),
mas a fase do ciclo contra a longitude ficou inconclusiva (salto de −0,56 ± 0,23 h na fronteira de fuso), porque o clima também desloca o
pico de temperatura. Por isso o teste decisivo foi o METAR.

Efeito do erro na base antiga:
- desde abril de 2021 (47% dos dados), toda hora estava deslocada em 3 a 5 h e 10% das leituras caíam no dia errado; 10% dos totais diários
  de chuva por estação mudam com a correção (SBGR, 01/10/2023: 64,9 → 45,1 mm; 18/04/2023: 19,9 → 46,9 mm);
- antes disso, as estações fora de UTC−3 estavam deslocadas em 1 ou 2 h (1% dos dias de chuva mudam).

Os oráculos pandas dos conjuntos de avaliação liam o mesmo relógio bruto como hora local, com o mesmo erro do sistema. Por isso a avaliação
nunca o detectou.

Correção (R1 em `ingest/transform.py`, D-115): o instante UTC sai da regra acima; a hora e o dia locais são os CIVIS da estação (zona IANA do
cadastro, com horário de verão onde e quando vigorou). Conferência da base corrigida: 94% a 100% de coincidência com o METAR em todas as
amostras (a amostra da transição, com dias faltando, dá 86%); a hora do pico de temperatura fica estável entre 13 h e 15 h locais em todos os
anos, quando antes saltava para 17 h a 19 h a partir de 2021.

## 2. Unidades: confirmadas

- Visibilidade em dezenas de metros: 100% dos valores estão nos degraus do METAR (50 m abaixo de 5 km, 100 m até 10 km, 1 km acima); 80% no
  teto de 2000 (20 km). Um valor de 9000 (90 km) vai para a quarentena pela faixa física.
- Base de nuvem em dezenas de metros: medianas por gênero ST 200 m, SC 600 m, CU 750 m, CB 1.050 m, AS 2,4 km, AC 3 km, CI 9 km, coerentes
  com a climatologia de cada gênero.

## 3. Boletins fora da hora cheia: comportamento de SPECI

6,7% dos boletins. Têm visibilidade abaixo de 5 km em 22% dos casos, contra 3% nos da hora cheia: são emitidos quando o tempo piora, como
SPECI. Não há marcação de correção (COR) na fonte.

## 4. Chuva: limitação da fonte, não corrigível na limpeza

Com mais de 90% das horas cobertas, os totais anuais de 2016 a 2025 ficam bem abaixo das normais climatológicas aproximadas em várias
estações: Salvador 39%, Recife 50%, Brasília 54%, Belo Horizonte 61%; Belém 85%, Guarulhos 85%, Manaus 115%. Os totais também variam muito
de um ano para outro sem falta de boletins (Guarulhos: 742 mm em 2018 e 1.834 mm em 2019). A causa provável é o registro da chuva no
boletim, não a ingestão. Toda resposta sobre chuva passou a trazer essa ressalva (`met:answerCaveat`).

## 5. Consistência entre variáveis: boa

Ponto de orvalho mais de 0,5 °C acima da temperatura em 347 de 8,4 milhões de pares (149 acima de 2 °C); bulbo úmido acima do seco em 15.
Pequeno demais para mudar respostas. Fica registrado, sem regra nova.

## O que continua em aberto

- Os códigos SBMI1–3, SDAM1–3, SIMK1–3 e XXXX não estão no cadastro; o fuso assumido é UTC−3.
- O mesmo instante pode ter várias leituras (até 4 por hora em temperatura desde 2021); as médias usam todas (R4).
- Deduplicação, faixas físicas e descarte de picos seguem como escolhas de engenharia, sem revisão meteorológica.
