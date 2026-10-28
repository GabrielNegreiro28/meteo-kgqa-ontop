# MVP `metqa` × v7 no conjunto novo_a_20261028 (medição com LLM real, 2026-10-28)

**Conjunto:** 50 perguntas escritas por outra IA (OpenAI GPT-6/Codex), congeladas com sha256 `8478a926…`.
- 40 respondíveis, 6 impossíveis, 4 ambíguas.
- Os 40 oráculos pandas foram executados duas vezes, por duas execuções independentes, com resultados iguais.
- Nenhuma regra do sistema foi alterada depois de ver o conjunto.

**Modelo:** `gpt-6-luna`, uma execução por condição. **Custo total:** US$ 2,33 (autorizado: US$ 3,5).

## Placar adjudicado

Comando: `python -m eval.adjudicate novo_a_20261028 …`. Vereditos em `docs/julgamento_novo_a_20261028_veredictos.yaml` (julgamento do Claude reproduzido nos CSV, sem revisão humana).

| Condição | Correto | **Errado entregue** | Absteve | IC95% | Custo |
|---|---|---|---|---|---|
| v7 (sistema anterior) | 36/50 | **4** | 10 | 58–83% | US$ 1,08 |
| **metqa** (MVP, léxico EvoOntology) | **37/50** | **0** | 13 | 60–84% | **US$ 0,62** |
| metqa-formal (MVP sem a camada EvoOntology) | 37/50 | 1 | 12 | 60–84% | US$ 0,64 |

- **Acerto:** nenhuma diferença é estatisticamente significativa (McNemar p = 1,00 em todos os pares; n = 50).
- **Erros entregues:**
  - o MVP entregou **zero** respostas erradas;
  - o v7 entregou 4:
    - E45: "No dia 13 de março de 2021" virou o mês inteiro, o mesmo defeito medido no novo_a, reproduzido num conjunto que nenhum dos dois viu;
    - E40: "Quanto choveu?" foi respondido sem estação nem período;
    - E41: "Como estava a temperatura" virou uma lista;
    - E35: uma previsão de 2027 virou "sem registros".
- **Custo:** o MVP custa 42% menos por pergunta, com uma chamada de LLM em vez de duas ou três.
- **Sem sinal sobre a camada EvoOntology:** metqa e metqa-formal empatam (2 × 2 discordantes). A camada publicada só acrescenta o sinônimo "choveu", e nenhuma pergunta deste conjunto o usa.

## Divergências que eram do oráculo, não do sistema

- **E13:** 7 das 8 leituras de "UR < 40%" são UR = 0,0 com temperatura de 29 °C e orvalho de 25 °C, ou seja, erro de sensor. A ingestão descarta UR fora de [1, 100]. A resposta do sistema (1) está certa.
- **E15:** a única leitura de orvalho abaixo de 10 °C é um pico isolado (22,0 → 6,7 → 22,2), descartado pela regra Q3. A resposta do sistema (0) está certa.
- **E23 e E46:** diferença de 0,02 a 0,04 °C. O oráculo faz a média das leituras duplicadas de cada instante, e o sistema mantém leituras distintas (D-87).

## Defeitos do MVP revelados pela medição (todos viraram abstenção, nenhum virou resposta errada)

| Perguntas | Defeito | Efeito |
|---|---|---|
| E03, E16, E22, E24, E27, E49 | Ano seguido de ponto ou vírgula ("no ano de 2018.", "Em 2019, …") não é lido: `spans._ANO` exclui `[.,]` depois do ano para não ler "2018.5" | A conciliação barrou o número sem dono (`NUMBER_UNUSED`) em vez de responder sobre todo o histórico. **A trava funcionou**, mas são 6 abstenções em perguntas que o v7 acertava |
| E47, E48 | Intervalo de horas explícito ("entre 0h e antes das 6h", "das 18h às 6h") não é lido | Barrado por `NUMBER_UNUSED` |
| E25 | A interpretação não trouxe exatamente uma grandeza (`ONE_MEASURE`) | Abstenção |
| E07, E18 | Altura da base de nuvem é atributo da camada de nuvens, não grandeza da ontologia | Lacuna de capacidade, dita pelos três sistemas |

Corrigir esses defeitos **depois** desta medição exige medir de novo num conjunto **novo**. Medir de novo neste conjunto seria viciado.
