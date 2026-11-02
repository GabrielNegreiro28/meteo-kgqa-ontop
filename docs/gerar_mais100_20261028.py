"""Nova rodada com 100 perguntas; não consulta regras do pipeline."""
from pathlib import Path
from collections import Counter
import re
import yaml

DOCS = Path(__file__).resolve().parent
TARGET = DOCS / 'perguntas_mais100_20261028.yaml'
QUESTIONS = []
SPECS = {
    'bseco': ('temperatura', -40, 60, '°C'),
    'bumido': ('temperatura', -40, 50, '°C'),
    'temppo': ('temperatura', -50, 40, '°C'),
    'ur': ('temperatura', 0, 100, '%'),
    'qnh': ('pressao', 870, 1085, 'hPa'),
    'visibpre': ('visibilidade', 0, 2000, 'dezenas de metros'),
    'velvento': ('vento', 0, 150, 'nós'),
    'rajada': ('vento', 0, 200, 'nós'),
    'precip': ('precipitacao', 0, 300, 'mm'),
    'durpreci': ('precipitacao', 0, 60, 'minutos'),
    'altnuvem': ('nuvem', 0, 2000, 'dezenas de metros'),
}


def add(cat, text, stations, start, end, col, expression, extra=None, full_hour=False):
    file, lo, hi, unit = SPECS[col]
    code = f'''import pandas as pd
stations = {stations!r}
parts = []
for chunk in pd.read_csv('{file}.csv', usecols=['sigla', 'hora_observacao', '{col}'], chunksize=100000):
    if stations is not None:
        chunk = chunk.loc[chunk['sigla'].isin(stations)]
    chunk = chunk.loc[(chunk['hora_observacao'] >= '{start}') & (chunk['hora_observacao'] < '{end}')].copy()
    parts.append(chunk)
d = pd.concat(parts, ignore_index=True)
d['hora_observacao'] = pd.to_datetime(d['hora_observacao'], errors='coerce')
d['{col}'] = pd.to_numeric(d['{col}'], errors='coerce')
d = d.loc[d['hora_observacao'].notna() & d['{col}'].between({lo}, {hi})]
'''
    note = (f'UTC−3 fixo; início inclusivo e fim exclusivo. Vazios, datas inválidas e '
            f'valores de {col} fora de [{lo}, {hi}] {unit} descartados. ')
    op = 'max' if file == 'vento' else 'min' if file == 'nuvem' else 'mean'
    code += f"d = d.groupby(['sigla', 'hora_observacao'], as_index=False)['{col}'].{op}()\n"
    note += {'max': 'Um boletim por estação e instante, usando o maior valor entre cabeceiras. ',
             'min': 'Um boletim por estação e instante, usando a menor base válida entre camadas; não equivale necessariamente ao teto. ',
             'mean': 'Duplicatas no mesmo instante reduzidas à média dos valores válidos. '}[op]
    if full_hour:
        code += "d = d.loc[(d['hora_observacao'].dt.minute == 0) & (d['hora_observacao'].dt.second == 0)]\n"
        note += 'Somente horas cheias para não somar janelas de chuva sobrepostas; lacunas não são preenchidas. '
    if col in ('visibpre', 'altnuvem'):
        code += f"d['{col}'] *= 10\n"
        note += 'Dezenas de metros convertidas para metros. '
        if col == 'visibpre':
            note += '2000 representa 20000 m ou mais, mantido como limite inferior de 20000 m. '
    if extra:
        setup, explanation = extra
        code += setup + '\n'
        note += explanation
    code += "assert not d.empty, 'Sem observações válidas após os filtros'\n"
    code += expression + '\n'
    QUESTIONS.append(dict(id=f'E{len(QUESTIONS)+51:02d}', category=cat, question=text,
        expected_behavior='answerable', rationale='A grandeza e o recorte pedidos estão disponíveis nos CSVs originais.',
        assumptions=note.strip(), oracle_pandas=code))


def scalar(cat, text, station, start, end, col, op, **kwargs):
    expression = (f"result = [(int(d['{col}'].count()),)]" if op == 'count' else
                  f"result = [(float(d['{col}'].{op}()),)]")
    add(cat, text, [station], start, end, col, expression, **kwargs)


# 24 simples: E51–E74.
SIMPLE = [
 ('Quanto marcou o menor bulbo úmido de SBAE em junho de 2016?', 'SBAE', '2016-06-01', '2016-07-01', 'bumido', 'min'),
 ('Em SBAN, qual foi a média do ponto de orvalho em setembro de 2017?', 'SBAN', '2017-09-01', '2017-10-01', 'temppo', 'mean'),
 ('Qual foi o QNH mais alto de SBBG em maio de 2018?', 'SBBG', '2018-05-01', '2018-06-01', 'qnh', 'max'),
 ('Quero saber a menor umidade relativa de SBBW em outubro de 2019.', 'SBBW', '2019-10-01', '2019-11-01', 'ur', 'min'),
 ('A que altura, em metros, estava a base de nuvem mais baixa de SBCB em abril de 2020?', 'SBCB', '2020-04-01', '2020-05-01', 'altnuvem', 'min'),
 ('Qual foi a rajada máxima de SBSC no ano de 2021, em nós?', 'SBSC', '2021-01-01', '2022-01-01', 'rajada', 'max'),
 ('Nos boletins de SBCJ de março de 2022, qual foi a maior duração de chuva em minutos?', 'SBCJ', '2022-03-01', '2022-04-01', 'durpreci', 'max'),
 ('Quantos milímetros de chuva foram registrados em SBDB em janeiro de 2023, somando apenas boletins de hora cheia?', 'SBDB', '2023-01-01', '2023-02-01', 'precip', 'sum'),
 ('Qual foi a menor visibilidade predominante de SBDO em julho de 2024, em metros?', 'SBDO', '2024-07-01', '2024-08-01', 'visibpre', 'min'),
 ('Em dezembro de 2025, qual a velocidade média do vento de SBES, em nós?', 'SBES', '2025-12-01', '2026-01-01', 'velvento', 'mean'),
 ('Qual foi a maior temperatura do ar de SBFN em novembro de 2016?', 'SBFN', '2016-11-01', '2016-12-01', 'bseco', 'max'),
 ('Quantos boletins de SBGP em fevereiro de 2017 têm valor válido de bulbo úmido?', 'SBGP', '2017-02-01', '2017-03-01', 'bumido', 'count'),
 ('Qual a média de umidade relativa registrada em SBGV entre 5 e 15 de agosto de 2018, com os dois dias incluídos?', 'SBGV', '2018-08-05', '2018-08-16', 'ur', 'mean'),
 ('Em SBIH, a pressão QNH média de abril de 2019 foi de quantos hPa?', 'SBIH', '2019-04-01', '2019-05-01', 'qnh', 'mean'),
 ('Qual o menor ponto de orvalho observado em SBIT em agosto de 2020?', 'SBIT', '2020-08-01', '2020-09-01', 'temppo', 'min'),
 ('Quero a temperatura do ar média de SBJD em outubro de 2021.', 'SBJD', '2021-10-01', '2021-11-01', 'bseco', 'mean'),
 ('Quanto atingiu a maior velocidade de vento registrada em SBJE em junho de 2022, em nós?', 'SBJE', '2022-06-01', '2022-07-01', 'velvento', 'max'),
 ('Qual foi o maior valor de bulbo úmido em SBJI em dezembro de 2023?', 'SBJI', '2023-12-01', '2024-01-01', 'bumido', 'max'),
 ('Qual a umidade relativa máxima de SBJR em fevereiro de 2024?', 'SBJR', '2024-02-01', '2024-03-01', 'ur', 'max'),
 ('Quantas observações de SBNM em setembro de 2025 informaram pressão QNH válida?', 'SBNM', '2025-09-01', '2025-10-01', 'qnh', 'count'),
 ('Qual a menor temperatura do ar em SBPC em julho de 2016?', 'SBPC', '2016-07-01', '2016-08-01', 'bseco', 'min'),
 ('Até quanto chegou a duração da chuva em um boletim de SBPB em março de 2017?', 'SBPB', '2017-03-01', '2017-04-01', 'durpreci', 'max'),
 ('Qual foi a visibilidade predominante mínima de SBPK em agosto de 2018, expressa em metros?', 'SBPK', '2018-08-01', '2018-09-01', 'visibpre', 'min'),
 ('Qual foi o QNH mínimo de SBRD em novembro de 2019?', 'SBRD', '2019-11-01', '2019-12-01', 'qnh', 'min'),
]
for text, station, start, end, col, op in SIMPLE:
    scalar('simples', text, station, start, end, col, op, full_hour=(col == 'precip'))

# 16 condições numéricas: E75–E90.
CONDITIONS = [
 ('Em quantos boletins de SBBI em 2016 o ponto de orvalho ficou abaixo de 5 °C?', 'SBBI', 2016, 'temppo', '< 5'),
 ('Quantas observações de SBBP em 2017 tiveram umidade relativa menor que 30%?', 'SBBP', 2017, 'ur', '< 30'),
 ('Conte as vezes em que o QNH de SBBU passou de 1020 hPa em 2018.', 'SBBU', 2018, 'qnh', '> 1020'),
 ('Em 2019, quantos boletins de SBCC registraram bulbo úmido acima de 25 °C?', 'SBCC', 2019, 'bumido', '> 25'),
 ('Quantos boletins de SBCN em 2020 apresentaram vento superior a 15 nós em pelo menos uma cabeceira?', 'SBCN', 2020, 'velvento', '> 15'),
 ('Em SBGM, quantas observações de 2021 indicaram visibilidade predominante abaixo de 3000 metros?', 'SBGM', 2021, 'visibpre', '< 3000'),
 ('Em quantos boletins de SBGW de 2022 havia base de nuvem inferior a 500 metros?', 'SBGW', 2022, 'altnuvem', '< 500'),
 ('Quantos registros de SBLS em 2023 informaram chuva com duração de pelo menos 45 minutos?', 'SBLS', 2023, 'durpreci', '>= 45'),
 ('Quantas observações de SBML em 2024 tiveram temperatura do ar igual ou superior a 32 °C?', 'SBML', 2024, 'bseco', '>= 32'),
 ('Em 2025, quantos boletins de SBMO apresentaram QNH abaixo de 1005 hPa?', 'SBMO', 2025, 'qnh', '< 1005'),
 ('Em quantos boletins de SBNT de 2016 o bulbo úmido foi inferior a 20 °C?', 'SBNT', 2016, 'bumido', '< 20'),
 ('Quantos boletins de SBPA em 2017 registraram rajada de pelo menos 25 nós?', 'SBPA', 2017, 'rajada', '>= 25'),
]
for text, station, year, col, condition in CONDITIONS:
    add('condicao', text, [station], f'{year}-01-01', f'{year+1}-01-01', col,
        f"result = [(int((d['{col}'] {condition}).sum()),)]")
for text, station, year, col, op, condition in [
 ('Em quantos dias de 2018 a mínima de temperatura do ar de SBPR ficou abaixo de 12 °C?', 'SBPR', 2018, 'bseco', 'min', '< 12'),
 ('Quantos dias de 2019 tiveram umidade relativa mínima abaixo de 25% em SBRP?', 'SBRP', 2019, 'ur', 'min', '< 25'),
 ('Em SBSJ, quantos dias de 2020 tiveram temperatura máxima acima de 30 °C?', 'SBSJ', 2020, 'bseco', 'max', '> 30'),
 ('Em 2021, em quantos dias SBSM teve pelo menos uma leitura de visibilidade predominante abaixo de 1000 metros?', 'SBSM', 2021, 'visibpre', 'min', '< 1000'),
]:
    add('condicao', text, [station], f'{year}-01-01', f'{year+1}-01-01', col,
        f"s = d.groupby(d['hora_observacao'].dt.date)['{col}'].{op}()\nresult = [(int((s {condition}).sum()),)]",
        extra=('', 'Contam-se datas locais com pelo menos uma observação válida; dias sem dados não contam.'))

# 16 séries ou rankings: E91–E106.
for text, station, year, col, op in [
 ('Mostre as temperaturas do ar mínimas mensais de SBSR em 2016.', 'SBSR', 2016, 'bseco', 'min'),
 ('Como ficaram as médias de bulbo úmido de SBST por mês de 2017?', 'SBST', 2017, 'bumido', 'mean'),
 ('Liste, em metros, a menor base de nuvem registrada em SBTA em cada mês de 2018.', 'SBTA', 2018, 'altnuvem', 'min'),
 ('Qual foi a duração máxima da chuva em um boletim de SBTB em cada mês de 2019?', 'SBTB', 2019, 'durpreci', 'max'),
 ('Preciso do ponto de orvalho médio de SBTC mês a mês em 2020.', 'SBTC', 2020, 'temppo', 'mean'),
 ('Qual a umidade relativa mínima de SBTD em cada mês de 2021?', 'SBTD', 2021, 'ur', 'min'),
 ('Mostre os máximos mensais de QNH de SBTF em 2022.', 'SBTF', 2022, 'qnh', 'max'),
 ('Como variou a velocidade média do vento de SBTG ao longo dos meses de 2023?', 'SBTG', 2023, 'velvento', 'mean'),
]:
    add('serie_ranking', text, [station], f'{year}-01-01', f'{year+1}-01-01', col,
        f"s = d.groupby(d['hora_observacao'].dt.month)['{col}'].{op}()\nresult = [(int(month), float(value)) for month, value in s.items()]",
        extra=('', 'Meses com dados válidos em ordem cronológica; meses ausentes omitidos.'))
for text, station, col, op in [
 ('Qual foi a maior temperatura do ar de SBTS em cada ano entre 2016 e 2025?', 'SBTS', 'bseco', 'max'),
 ('De 2016 até 2025, apresente a pressão QNH média anual de SBUF.', 'SBUF', 'qnh', 'mean'),
 ('Quais as menores visibilidades predominantes de SBUY por ano, de 2016 a 2025, em metros?', 'SBUY', 'visibpre', 'min'),
 ('Quero as médias anuais de bulbo úmido de SBUL entre 2016 e 2025.', 'SBUL', 'bumido', 'mean'),
]:
    add('serie_ranking', text, [station], '2016-01-01', '2026-01-01', col,
        f"s = d.groupby(d['hora_observacao'].dt.year)['{col}'].{op}()\nresult = [(int(year), float(value)) for year, value in s.items()]",
        extra=('', 'Anos com dados válidos em ordem cronológica; anos ausentes omitidos.'))
for text, year, col, op, asc, n in [
 ('Quais cinco estações tiveram os maiores valores de bulbo úmido em 2024?', 2024, 'bumido', 'max', False, 5),
 ('Em 2025, quais foram as cinco estações com menor QNH médio?', 2025, 'qnh', 'mean', True, 5),
 ('Qual estação registrou a maior velocidade de vento em 2018?', 2018, 'velvento', 'max', False, 1),
 ('Quais três estações apresentaram as maiores médias de ponto de orvalho em 2019?', 2019, 'temppo', 'mean', False, 3),
]:
    add('serie_ranking', text, None, f'{year}-01-01', f'{year+1}-01-01', col,
        f"s = d.groupby('sigla')['{col}'].{op}().reset_index(name='value')\ns = s.sort_values(['value', 'sigla'], ascending=[{asc}, True]).head({n})\nresult = [(str(row.sigla), float(row.value)) for row in s.itertuples()]",
        extra=('', 'Todas as siglas com ao menos uma observação válida, inclusive identificadores especiais; sem exigência de cobertura mínima. Empates ordenados pela sigla.'))

# 8 comparações: E107–E114.
for text, stations, start, end, col, op in [
 ('Como se comparam as mínimas de temperatura do ar de SBAR e SBJP em julho de 2024?', ['SBAR', 'SBJP'], '2024-07-01', '2024-08-01', 'bseco', 'min'),
 ('Compare o QNH médio de SBBE com o de SBSN em maio de 2025.', ['SBBE', 'SBSN'], '2025-05-01', '2025-06-01', 'qnh', 'mean'),
 ('Qual foi o bulbo úmido médio de SBCG em comparação com SBCY em setembro de 2016?', ['SBCG', 'SBCY'], '2016-09-01', '2016-10-01', 'bumido', 'mean'),
 ('Compare o menor ponto de orvalho de SBFL e SBCT em agosto de 2017.', ['SBFL', 'SBCT'], '2017-08-01', '2017-09-01', 'temppo', 'min'),
]:
    add('comparacao', text, stations, start, end, col,
        f"s = d.groupby('sigla')['{col}'].{op}()\nassert set(s.index) == set(stations)\nresult = [(str(station), float(value)) for station, value in s.items()]")
for text, station, years, month, col, op in [
 ('O QNH mínimo de SBFI em junho foi quanto em 2018 e em 2023?', 'SBFI', [2018, 2023], 6, 'qnh', 'min'),
 ('Compare a umidade relativa média de SBFZ em novembro de 2019 e novembro de 2024.', 'SBFZ', [2019, 2024], 11, 'ur', 'mean'),
 ('Como diferem os máximos de velocidade do vento de SBGO em agosto de 2020 e de 2025?', 'SBGO', [2020, 2025], 8, 'velvento', 'max'),
 ('Compare as médias de bulbo úmido de SBGR em fevereiro de 2021 e de 2022.', 'SBGR', [2021, 2022], 2, 'bumido', 'mean'),
]:
    add('comparacao', text, [station], f'{min(years)}-01-01', f'{max(years)+1}-01-01', col,
        f"d = d.loc[(d['hora_observacao'].dt.month == {month}) & d['hora_observacao'].dt.year.isin({years})]\ns = d.groupby(d['hora_observacao'].dt.year)['{col}'].{op}()\nassert set(s.index) == set({years})\nresult = [(int(year), float(value)) for year, value in s.items()]")


def no_oracle(cat, text, why):
    QUESTIONS.append(dict(id=f'E{len(QUESTIONS)+51:02d}', category=cat, question=text,
        expected_behavior='unsupported' if cat == 'impossivel' else 'needs_clarification',
        rationale=why, assumptions='nenhuma'))


# 12 não suportadas: E115–E126.
for text, why in [
 ('A estação SBVC pertence a qual município?', 'Não há cadastro de municípios nos arquivos.'),
 ('Em que estado brasileiro está SDAM?', 'Não há relação entre siglas e estados nos CSVs.'),
 ('Qual é a longitude de SSKW?', 'Longitude não está entre as colunas disponíveis.'),
 ('A quantos metros de altitude está o aeródromo SBPO?', 'Altitude da estação não é fornecida.'),
 ('Qual a previsão de chuva para SBPV em 7 de fevereiro de 2027?', 'Os dados históricos não fornecem previsões.'),
 ('Qual será a visibilidade predominante em SBRF às 8h de 1º de janeiro de 2028?', 'Não há observações futuras nem produto de previsão.'),
 ('Quanta radiação ultravioleta SBVT recebeu em dezembro de 2022?', 'Radiação ultravioleta não foi medida nas colunas fornecidas.'),
 ('Qual foi a concentração média de material particulado em SBRJ em julho de 2021?', 'Não há medições de qualidade do ar.'),
 ('Qual foi a temperatura do ar máxima de SBSP em janeiro de 2014?', 'O período antecede o início de 2016.'),
 ('Qual a pressão QNH média de SBGL em março de 2026?', 'O período ultrapassa o término da série em 2025.'),
 ('Quantos milímetros de chuva a estação ZZXQ registrou em 2020?', 'ZZXQ não está na lista extraída dos CSVs.'),
 ('Qual foi a velocidade máxima do vento na estação QQQZ em 2024?', 'QQQZ não está na lista extraída dos CSVs.'),
]:
    no_oracle('impossivel', text, why)

# 8 ambíguas: E127–E134.
for text, why in [
 ('Qual foi a melhor época para operar em SBKP?', 'Faltam período e critério meteorológico para melhor época.'),
 ('A umidade estava baixa em SBLE?', 'Faltam o período e o limiar para umidade baixa.'),
 ('Me mostre as maiores temperaturas do ano.', 'Faltam estação, ano e quantidade de resultados desejada.'),
 ('Como ficou a pressão de SBLJ naquele mês?', 'O mês e o ano referidos não foram informados.'),
 ('Quanto tempo durou a chuva em SBLP?', 'Faltam o período e a agregação da duração dos boletins.'),
 ('Compare o tempo de SBMI e SDCO.', 'Faltam o período e as grandezas ou critérios para a comparação.'),
 ('A visibilidade estava boa em SBIP em maio de 2018?', 'É necessário esclarecer o critério para boa visibilidade e como resumir o mês.'),
 ('Qual foi a base de nuvem em SBJC em 2020?', 'Falta especificar o instante ou a estatística e como selecionar as camadas.'),
]:
    no_oracle('ambigua', text, why)

# 8 informais: E135–E142.
for text, station, start, end, col, op in [
 ('qual foi a umidade relativa mais baixa em sbaf em outubro de 2016?', 'SBAF', '2016-10-01', '2016-11-01', 'ur', 'min'),
 ('Me passa a média da temperatua do ar de SBAQ em janeiro de 2017.', 'SBAQ', '2017-01-01', '2017-02-01', 'bseco', 'mean'),
 ('Em vinte e dois de maio de 2018, qual foi o maior QNH de SBAX?', 'SBAX', '2018-05-22', '2018-05-23', 'qnh', 'max'),
 ('Do ponto de orvalho de SBCA em junho de 2019, eu queria só a média.', 'SBCA', '2019-06-01', '2019-07-01', 'temppo', 'mean'),
 ('O vento em sbco chegou a quantos nós no máximo em setembro de 2020?', 'SBCO', '2020-09-01', '2020-10-01', 'velvento', 'max'),
 ('Dá uma olhada: qual a menor visibildade predominante de SBCP em abril de 2021, em metros?', 'SBCP', '2021-04-01', '2021-05-01', 'visibpre', 'min'),
 ('Em SBES, no dia cinco de fevereiro de 2022, qual foi a média de bulbo úmido?', 'SBES', '2022-02-05', '2022-02-06', 'bumido', 'mean'),
 ('preciso da menor temperatura do ar de sbmg em julho de 2023, valeu!', 'SBMG', '2023-07-01', '2023-08-01', 'bseco', 'min'),
]:
    scalar('informal', text, station, start, end, col, op)

# 8 recortes temporais: E143–E150.
scalar('tempo', 'Nos sábados e domingos de 2016, qual foi a temperatura do ar média de SBBR?', 'SBBR', '2016-01-01', '2017-01-01', 'bseco', 'mean',
    extra=("d = d.loc[d['hora_observacao'].dt.dayofweek >= 5]", 'Fim de semana definido por sábado e domingo na data local.'))
scalar('tempo', 'Qual o QNH mínimo de SBEG nas madrugadas de maio de 2017, entre meia-noite e antes das 6h?', 'SBEG', '2017-05-01', '2017-06-01', 'qnh', 'min',
    extra=("d = d.loc[d['hora_observacao'].dt.hour < 6]", 'Madrugada no intervalo local [00:00, 06:00).'))
scalar('tempo', 'Qual a umidade relativa média de SBMA nas tardes de agosto de 2018, das 12h até antes das 18h?', 'SBMA', '2018-08-01', '2018-09-01', 'ur', 'mean',
    extra=("d = d.loc[d['hora_observacao'].dt.hour.between(12, 17)]", 'Tarde no intervalo local [12:00, 18:00).'))
scalar('tempo', 'Durante as noites de julho de 2019, das 18h às 6h, qual foi a menor visibilidade predominante de SBME, em metros?', 'SBME', '2019-07-01', '2019-08-01', 'visibpre', 'min',
    extra=("h = d['hora_observacao'].dt.hour\nd = d.loc[(h >= 18) | (h < 6)]", 'Noite: [18:00, 24:00) ou [00:00, 06:00); julho pela data local de cada leitura.'))
scalar('tempo', 'No segundo trimestre de 2020, qual foi o bulbo úmido médio de SBMT?', 'SBMT', '2020-04-01', '2020-07-01', 'bumido', 'mean',
    extra=('', 'Segundo trimestre compreende abril, maio e junho completos.'))
scalar('tempo', 'Qual a maior temperatura do ar de SBPS no verão de 2022, considerando janeiro, fevereiro e março?', 'SBPS', '2022-01-01', '2022-04-01', 'bseco', 'max',
    extra=('', 'O verão é operacionalmente definido na própria pergunta como os três primeiros meses completos de 2022.'))
scalar('tempo', 'Em dias de segunda a sexta de 2024, qual a velocidade média do vento de SBRB, em nós?', 'SBRB', '2024-01-01', '2025-01-01', 'velvento', 'mean',
    extra=("d = d.loc[d['hora_observacao'].dt.dayofweek < 5]", 'Segunda a sexta pela data local, incluindo feriados.'))
scalar('tempo', 'Qual o ponto de orvalho mínimo de SBVC nas manhãs de setembro de 2025, das 6h até antes do meio-dia?', 'SBVC', '2025-09-01', '2025-10-01', 'temppo', 'min',
    extra=("d = d.loc[d['hora_observacao'].dt.hour.between(6, 11)]", 'Manhã no intervalo local [06:00, 12:00).'))


if __name__ == '__main__':
    expected = dict(simples=24, condicao=16, serie_ranking=16, comparacao=8,
                    impossivel=12, ambigua=8, informal=8, tempo=8)
    assert Counter(q['category'] for q in QUESTIONS) == expected
    assert [q['id'] for q in QUESTIONS] == [f'E{i:02d}' for i in range(51, 151)]
    assert len({q['question'].casefold() for q in QUESTIONS}) == 100
    assert sum('oracle_pandas' in q for q in QUESTIONS) == 80
    for q in QUESTIONS:
        if 'oracle_pandas' in q:
            compile(q['oracle_pandas'], q['id'], 'exec')
    class Dumper(yaml.SafeDumper):
        pass
    Dumper.add_representer(str, lambda dumper, value: dumper.represent_scalar(
        'tag:yaml.org,2002:str', value, style='|' if '\n' in value else None))
    with TARGET.open('x', encoding='utf-8', newline='\n') as stream:
        yaml.dump({'questions': QUESTIONS}, stream, Dumper=Dumper, allow_unicode=True, sort_keys=False, width=120)
    print(f'{TARGET.name}: 100 perguntas; 80 oráculos compilados.')
