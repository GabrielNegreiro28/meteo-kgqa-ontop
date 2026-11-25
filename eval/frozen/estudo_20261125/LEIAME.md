# Conjunto do estudo estudo_20261125 (congelado antes de qualquer execução)

- 120 perguntas inéditas (80 respondíveis, 20 de esclarecimento, 20 fora do escopo), escritas por um agente separado (Claude Sonnet 5.5) que
  leu só `docs/PROMPT_ESTUDO_PERGUNTAS.md` e `data/estacoes.csv` e consultou a base limpa em modo leitura; não viu o código nem conjuntos antigos.
- Referências: SQL do gerador sobre a camada limpa (`referencias.json`), convertido por `eval.study_references` (só acrescenta a unidade
  canônica) e executado por `eval.clean_reference` no snapshot `snapshot.json` (`referencias_congeladas.json`). Oráculo e sistema leem a
  MESMA base limpa: o placar mede a consulta, não a limpeza.
- Agenda sem LLM: `eval/reports/estudo_20261125_agenda/manifest.json` (5 condições × 3 repetições × 120 = 1.800 execuções).

## Conflitos previstos, registrados antes de rodar

Conferidos contra a convenção de lugar do sistema (D-117) e o cadastro, sem executar o sistema. Nem o conjunto nem o sistema foram mudados
por causa deles; o placar deve contá-los como estão.
- Cidade com duas estações e referência com uma só (o sistema deve pedir esclarecimento): S009 (Manaus: SBEG e SBMN); S037, S057 e S096
  (Goiânia: SBGO e SBNV; S057 cita "Santa Genoveva", que não é apelido no cadastro).
- Nome que o cadastro não reconhece: S003 e S006 ("Floripa"), S024 e S065 ("Natal (base aérea)": SBNT fica em Parnamirim), S110 ("Cuiabá":
  SBCY fica em Várzea Grande).
- Dúvidas do próprio gerador: S080 (visibilidade mínima 0 m no Galeão em 2017), S111 (as duas partes empatam em 41,3 °C).

Melhorias que esses casos sugerem (cidade atendida como menção, apelidos populares) ficam para DEPOIS da medição neste conjunto.
