# Dicionário e relações — dados meteorológicos reais (pasta METEOROLOGIA)

Levantado em 14/10/2026 a partir dos próprios CSVs (perfil completo de todos os arquivos + testes de
consistência física). Confiança: **C** = confirmado nos dados; **H** = hipótese forte, confirmar com o professor.

Origem provável: produto CLIMAER Superfície do ICEA/DECEA (estações meteorológicas de superfície de
aeródromos), que lista exatamente CGT, nuvens, precipitação, pressão, temperatura, vento e visibilidade. (H)

## Visão geral
| Arquivo | Linhas | Chave | Linhas por chave |
|---|---|---|---|
| temperatura.csv | 10.307.346 | (sigla, hora_observacao) | 1, ou 2+ em aeródromos com mais de uma pista |
| vento.csv | 13.224.256 | (sigla, hora_observacao, cabeceira) | uma por cabeceira de pista |
| nuvem.csv | 12.648.891 | (sigla, hora_observacao, camada) | uma por camada de nuvem; nenhuma se céu sem nuvens |
| nuvem_COLUNAS.csv | ~derivado | (sigla, hora_obs) | pivot de nuvem.csv — **não ingerir** |
| precipitacao.csv | 8.210.344 | (sigla, hora_observacao) | 1 |
| pressao.csv | 8.638.937 | (sigla, hora_observacao) | 1 |
| visibilidade.csv | 8.638.728 | (sigla, hora_observacao) | 1 |
| cgt.csv | 1 | — | arquivo-amostra (1 linha), separador `;` |

- 178 códigos de estação (ICAO: SB.., SD.., SI.., SN.., SS.., SW..), 2016-01-01 a 2025-12-31.
- Observações horárias em :00 (~94 %) mais boletins extras em outros minutos (prováveis SPECI). (C / H para SPECI)
- **Não há cadastro de estações** (nome, cidade, UF, lat/lon, altitude, fuso). Precisa de fonte externa.

## Relação central (C)
Todos os arquivos compartilham a chave **(sigla, hora_observacao)**: cada chave é **um boletim de observação**
de uma estação num instante, e cada arquivo descreve um aspecto desse boletim. Na amostra SBGR+SBBE/2019,
as 18.766 chaves de temperatura, visibilidade, precipitação e vento coincidem com as de pressão (±2);
nuvem cobre 15.946 (as demais são céu sem nuvens reportadas).

```
Estação (sigla) 1──N Boletim (sigla, hora) 1──1 pressão, visibilidade, precipitação
                                            1──1..N temperatura (N = pistas; só temppista varia)
                                            1──N vento (uma linha por cabeceira)
                                            1──0..N camada de nuvem
```

## Tempo (H — o ponto mais importante a confirmar)
- `hora_observacao` **não está em UTC**: o ciclo diurno médio tem máximo ~15h e mínimo ~6h (em UTC seriam ~18h e ~9h).
- Comporta-se como **hora de Brasília padrão (UTC−3) aplicada a todas as estações**, inclusive Manaus e Rio Branco.
- Artefato de horário de verão: nas datas de início do HV (2016-10-16, 2017-10-15, 2018-11-04) não há hora 00:xx
  e a hora 01:00 aparece duplicada em todas as estações ativas (inclusive as que nunca tiveram HV). Padrão típico de
  "localizar" horário UTC−3 em America/Sao_Paulo com deslocamento da hora inexistente.
- Regra provisória de ingestão: UTC = hora + 3 h; os pares duplicados das 01:00 nessas 3 datas vão para quarentena
  (um deles é a observação das 00:00, mas não dá para saber qual).

## Variáveis
| Arquivo.coluna | Significado | Unidade | Tipo | Conf. | Observações |
|---|---|---|---|---|---|
| temperatura.bseco | temperatura do ar (bulbo seco) | °C | instantânea | C | erros: máx 79,8 |
| temperatura.bumido | temperatura de bulbo úmido | °C | instantânea | C | sempre ≤ bseco |
| temperatura.ur | umidade relativa | % | instantânea | C | 0–100 |
| temperatura.temppo | temperatura do ponto de orvalho | °C | instantânea | C | bate com Magnus(T, UR): mediana 0,03 °C; erros −68,3 e 93 |
| temperatura.temppista | temperatura da pista | °C | instantânea | H | 94 % vazio; varia entre linhas da mesma chave, sem indicar a pista |
| pressao.qnh | pressão QNH (reduzida ao nível do mar, padrão ICAO) | hPa | instantânea | C | erros: 0 e 9852,6 |
| visibilidade.visibpre | visibilidade predominante | **dezenas de metros** | instantânea | H | degraus 5/10/100 = 50 m/100 m/1 km, como no METAR; 2000 = 20 km (teto, 80 % dos casos) |
| precipitacao.precip | precipitação na última hora | mm | **acumulada** (1 h) | C/H | soma anual bate com a climatologia (SBBE 3.196 mm, SBGR 1.834 mm em 2019); boletins fora da hora cheia têm 0 ou vazio — não somar em duplicidade |
| precipitacao.durpreci | duração da precipitação na hora | min | acumulada | H | 0–60 (máx 91 = erro) |
| vento.cabeceira | cabeceira de pista do anemômetro | — | identificador | C | "09R", "27L", "15/33"… |
| vento.velvento | velocidade média do vento | **nós (kt)** | instantânea | C | rajada só reportada quando ≥ 10 acima da média: regra do METAR em kt |
| vento.dirvento | direção de onde sopra o vento | **dezenas de graus** | instantânea | C | 0 = calmaria (sempre com vel 0); 99 = variável (VRB) |
| vento.rajada | rajada | kt | instantânea | C | 99 % vazio |
| nuvem.qtdnuvem | cobertura da camada | oitavos (oktas) | instantânea | H | 1–8; 9 e 10 raros (céu obscurecido?) |
| nuvem.altnuvem | altura da base da camada | **dezenas de metros** | instantânea | H | medianas por tipo: ST 20, SC 60, CU 75, CB 105, AC 300, CI 900 → 200 m…9 km |
| nuvem.tipo_nuvem | gênero da nuvem | código | categoria | C | CU, SC, AC, ST, CI, "CI e/ou CC", AS, TCU, CB, CS, NS; "/" e "X" = não observável |
| nuvem.direcao_nuvem | direção de deslocamento da nuvem | rumo | categoria | H | N…NW; "UK" = desconhecida; "0" e "X" = sem/indeterminada |
| nuvem_COLUNAS.altura_nuvem_N | altura da camada com N oitavos | dam | — | C | pivot de nuvem.csv por qtdnuvem; perde tipo/direção e colide quando duas camadas têm o mesmo N |
| nuvem_COLUNAS.visibilidade | — | — | — | — | vazia na amostra |
| cgt.cgt_1..3 | condição geral do tempo | código | categoria | H | provável tabela de tempo presente da OMM (ww); só 1 linha no arquivo |

## Qualidade e anomalias
- Siglas suspeitas: `XXXX`, `SBMI1–3`, `SDAM1–3`, `SIMK1–3` (poucas linhas). Tratar como estações distintas
  até confirmar; não fundir com SBMI/SDAM/SIMK.
- Valores fisicamente impossíveis (para quarentena via SHACL): qnh 0 e 9852,6; bseco 79,8; temppo −68,3/93;
  velvento 993; rajada 341; precip 790 mm/h.
- Chaves duplicadas fora do esperado: além do horário de verão, ~1,4 mi de grupos repetidos em temperatura, a maioria
  explicada por temperatura de pista em aeródromos com várias pistas; crescem a partir de 2021 (verificar).
- Vazio ≠ zero em todas as colunas (ex.: precip vazio em ~500 mil boletins).

## Volume e consequência para o grafo
~10 mi de boletins × ~15 variáveis. Modelado em SOSA (uma observação por variável), daria centenas de milhões de
observações e alguns bilhões de triplas: inviável em rdflib e pesado mesmo para um triple store.
Alternativas a decidir: grafo virtual (Ontop sobre DuckDB/CSV, mapeamento R2RML para a ontologia — alinhado com a
arquitetura do professor), materialização de um recorte, ou modelo mais compacto (boletim como nó com vários resultados).

## Perguntas ao professor
1. Os horários são hora de Brasília (UTC−3) para todas as estações? Como foi feita a conversão de UTC?
2. Confirma as unidades: visibilidade e altura de nuvem em dezenas de metros, vento em nós, direção em dezenas de graus?
3. Existe cadastro das estações (nome, município, UF, coordenadas, altitude)?
4. O que são SBMI1–3, SDAM1–3, SIMK1–3 e XXXX?
5. Boletins fora da hora cheia são SPECI? Há indicação de correção (COR)?
6. Qual tabela de códigos usa o CGT? O cgt.csv completo existe?
