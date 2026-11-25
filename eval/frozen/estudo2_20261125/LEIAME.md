# Conjunto estudo2_20261125 (congelado antes de qualquer execução)

- 120 perguntas inéditas (80 respondíveis, 20 de esclarecimento, 20 fora do escopo), escritas por um segundo agente separado (Claude
  Sonnet 5.5) que leu só `docs/PROMPT_ESTUDO_PERGUNTAS.md` e `data/estacoes.csv` e consultou a base limpa em modo leitura; não viu o código,
  o conjunto estudo_20261125 nem os resultados dele.
- Referências: SQL do gerador sobre a camada limpa, convertido por `eval.study_references` e executado por `eval.clean_reference` no
  snapshot `snapshot.json` (artefatos do branch `correcoes-estudo`, com as diretrizes gerais de D-122).
- Agenda: `eval/reports/estudo2_20261125_agenda/manifest.json` (condição completa, uma repetição), com os hashes das entradas.
- Rodada prevista: gpt-6.2-sol, esforço medium, verba de US$ 10.
- Dúvidas do próprio gerador: QNH de 921 hPa em SBJI (2017) parece erro de dado; rankings dependem de estações com cobertura parcial;
  4 respondíveis têm resposta "sem registros" (SBPR 2024, SBJC 2023, temperatura de pista em SBCN 2025, SBFN 2022).
