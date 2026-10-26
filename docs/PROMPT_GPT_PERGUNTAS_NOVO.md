# Prompt para gerar o conjunto NOVO de avaliação (A1/A3 de PLANO_ABLACAO.md)

Como usar: (1) rode o comando abaixo para listar as estações; (2) cole o PROMPT no GPT (de preferência um modelo diferente do que roda no pipeline) e,
no lugar de `<<LISTA_DE_ESTACOES>>`, cole a saída do comando; (3) salve a resposta SEM editar as perguntas; (4) só depois entregue o arquivo para a validação.
Não mostre ao GPT as regras do pipeline, o `DECISOES.md` nem os conjuntos antigos.

```powershell
# lista de estações (siglas) e primeiro/último dia com dados, a partir dos CSV originais
python -c "import pandas as pd; d=pd.read_csv(r'C:\Users\Gabriel\OneDrive\Área de Trabalho\Parente\METEOROLOGIA\pressao.csv', usecols=['sigla','hora_observacao']); g=d.groupby('sigla').hora_observacao.agg(['min','max','count']); print(g.to_string())"
```

---

## PROMPT (cole a partir daqui)

Você vai criar um conjunto de avaliação para um sistema de perguntas e respostas em português sobre dados meteorológicos de aeródromos brasileiros.
Você NÃO conhece o sistema e não deve tentar adivinhar como ele funciona. Escreva as perguntas como pessoas reais as fariam: um meteorologista,
um controlador, um analista de dados, um estudante. Seu trabalho é criar perguntas variadas, realistas e verificáveis, com a resposta correta calculada
por código independente sobre os arquivos originais.

### Os dados (é só isto que existe)
Arquivos CSV, 178 estações (siglas ICAO), de 01/01/2016 a 31/12/2025, observações horárias (mais alguns boletins fora da hora cheia).
Todos têm as colunas `sigla` (estação) e `hora_observacao` (data e hora; hora local fixa de Brasília, UTC−3, para todas as estações).

| Arquivo | Colunas de valor | Significado e unidade |
|---|---|---|
| temperatura.csv | `bseco`, `bumido`, `ur`, `temppo`, `temppista` | temperatura do ar (°C), bulbo úmido (°C), umidade relativa (%), ponto de orvalho (°C), temperatura da pista (°C, quase sempre vazia) |
| pressao.csv | `qnh` | pressão QNH em hPa |
| visibilidade.csv | `visibpre` | visibilidade predominante em **dezenas de metros** (2000 = 20 km ou mais) |
| precipitacao.csv | `precip`, `durpreci` | chuva na última hora (mm); duração da chuva na hora (min) |
| vento.csv | `cabeceira`, `velvento`, `dirvento`, `rajada` | uma linha por cabeceira de pista; velocidade em nós; direção em **dezenas de graus** (0 = calmaria, 99 = variável); rajada em nós (quase sempre vazia) |
| nuvem.csv | `camada`, `qtdnuvem`, `altnuvem`, `tipo_nuvem`, `direcao_nuvem` | uma linha por camada de nuvem; cobertura em oitavos; altura da base em **dezenas de metros**; gênero (CU, SC, AC, ST, CI, CB, TCU…) |

Observações importantes: não há cadastro com nome de cidade, estado, latitude ou altitude das estações, só a sigla. Há valores vazios (vazio não é zero)
e alguns valores claramente impossíveis (erros de sensor). A lista de estações e o período de cada uma está abaixo:

<<LISTA_DE_ESTACOES>>

### O que produzir
Crie **50 perguntas** em português, distribuídas assim (use estações e períodos variados, só dentro do que os dados cobrem):

1. **12 perguntas simples respondíveis**: valor único (média, máximo, mínimo, total, contagem) de uma grandeza, uma estação, um período (ano, mês, dia, intervalo).
2. **8 perguntas com condição numérica**: "quantas vezes passou de…", "quantas horas abaixo de…", "em quantos dias a temperatura máxima ficou acima de…".
3. **8 perguntas de série ou ranking**: por mês, por ano, "as 5 estações mais…", "em que mês… mais", "qual a estação com maior…" (ranking entre estações).
4. **4 perguntas de comparação** entre duas estações ou dois períodos.
5. **6 perguntas que o sistema NÃO deveria conseguir responder** porque os dados não têm a informação: nome de cidade ou estado, latitude, previsão do futuro, uma grandeza que não existe (ex.: radiação solar), período fora de 2016–2025, estação que não está na lista.
6. **4 perguntas ambíguas** que exigem esclarecimento (ex.: "qual foi o pior dia?", "está quente?", sem estação e sem período, uma grandeza que pode ser duas coisas).
7. **4 perguntas escritas de modo informal ou com variação**: gíria leve, erro de digitação ("temperatua"), sigla em minúsculas, data por extenso ("13 de março de 2021"), ordem das palavras diferente.
8. **4 perguntas com condição de tempo diferente**: "no verão de 2022", "de madrugada", "no primeiro trimestre", "durante a noite", "nos fins de semana".

Regras para as perguntas:
- Cada pergunta deve ser natural e **independente**; não repita o molde de frase das outras.
- Varie as estações e os anos; não concentre tudo em poucas estações.
- Perguntas respondíveis precisam ter resposta calculável nos arquivos acima. Não invente colunas.
- Não escreva a pergunta de modo a "ajudar" um sistema; escreva como um usuário.

### Formato da resposta (YAML, nada além do YAML)
```yaml
questions:
- id: E01
  category: simples | condicao | serie_ranking | comparacao | impossivel | ambigua | informal | tempo
  question: "texto da pergunta"
  expected_behavior: answerable | unsupported | needs_clarification
  rationale: "uma frase: por que é respondível, impossível ou ambígua"
  assumptions: "como você tratou unidade, vazios, valores impossíveis, hora local, múltiplas linhas por boletim (ou 'nenhuma')"
  oracle_pandas: |
    # só para answerable: código pandas que lê os CSV originais e termina com
    # result = [ (valor1, valor2, ...), ... ]   # uma tupla por linha de resposta
    # use pd.read_csv com usecols; converta unidades; trate vazios e outliers explicitamente
```
Para `unsupported` e `needs_clarification`, omita `oracle_pandas`.

### Código de referência (oracle_pandas)
- Leia só os CSV originais e use apenas as colunas listadas.
- Converta unidades no código (por exemplo, visibilidade para metros, direção para graus) e diga isso em `assumptions`.
- Se houver mais de uma linha por (estação, hora) por causa de pistas ou cabeceiras, diga em `assumptions` se você contou linhas ou boletins.
- Descarte valores impossíveis com um limite físico razoável e declare o limite em `assumptions`.
- O código deve ser curto, legível e rodar em uma máquina com memória limitada (use `usecols` e filtre por estação logo ao ler).

### Cuidados para este conjunto (é a segunda rodada)
- Já existe outro conjunto de avaliação que você não viu. Evite as perguntas mais óbvias ("temperatura média de SBGL em 2020"): prefira combinações menos óbvias de estação, grandeza e período.
- Use pelo menos 25 estações diferentes e todos os anos de 2016 a 2025.
- Inclua grandezas menos comuns (bulbo úmido, ponto de orvalho, rajada, nuvem, duração da chuva), não só temperatura e chuva.
- Uma pergunta por ideia: não encadeie duas perguntas numa só.

Gere agora as 50 perguntas.

---

## Depois do GPT responder
1. Salve como `perguntas_novas.yaml` **sem editar**; congele com `python -m eval.freeze_set perguntas_novas.yaml --name novo_a --source "<modelo gerador>"`.
2. Revise só o que não faz sentido (pergunta repetida, sem resposta nos dados, `expected_behavior` obviamente errado); registre cada remoção com o motivo.
3. A validação executa cada `oracle_pandas` (isolado, com limite de tempo), descarta o que der vazio ou erro e congela o conjunto com um hash antes de qualquer execução do pipeline.
4. Ao medir, as respostas do pipeline que **divergirem** do código do GPT vão para julgamento humano: pode ser erro do pipeline, erro do código de referência, ou decisão de limpeza (valor impossível, fuso, múltiplas leituras) que precisa ser declarada.
