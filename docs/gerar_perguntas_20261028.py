"""Geração independente: não consulta regras nem perguntas anteriores."""
from pathlib import Path
from collections import Counter
import re
import yaml

OUT = Path(__file__).resolve().parent
TARGET = OUT / 'perguntas_novas_20261028.yaml'
QUESTIONS = []
LIMITS = {'bseco': (-40, 60), 'bumido': (-40, 50), 'temppo': (-50, 40),
          'ur': (0, 100), 'qnh': (870, 1085), 'visibpre': (0, 2000),
          'velvento': (0, 150), 'rajada': (0, 200), 'precip': (0, 300),
          'durpreci': (0, 60), 'altnuvem': (0, 2000)}
FILES = {'bseco': 'temperatura', 'bumido': 'temperatura', 'temppo': 'temperatura',
         'ur': 'temperatura', 'qnh': 'pressao', 'visibpre': 'visibilidade',
         'velvento': 'vento', 'rajada': 'vento', 'precip': 'precipitacao',
         'durpreci': 'precipitacao', 'altnuvem': 'nuvem'}


def add(category, question, stations, start, end, col, expression, extra='', full_hour=False):
    lo, hi = LIMITS[col]
    file = FILES[col]
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
    note = (f'Hora local fixa UTC−3, intervalos com início inclusivo e fim exclusivo; '
            f'vazios e valores fora de [{lo}, {hi}] em {col} descartados. ')
    if file == 'vento':
        code += f"d = d.groupby(['sigla', 'hora_observacao'], as_index=False)['{col}'].max()\n"
        note += 'Um boletim por estação e instante; usa-se o maior valor entre cabeceiras, sem contá-las separadamente. '
    elif file == 'nuvem':
        code += f"d = d.groupby(['sigla', 'hora_observacao'], as_index=False)['{col}'].min()\n"
        note += 'Um boletim por estação e instante; menor base válida entre todas as camadas, sem exigir cobertura de teto. '
    else:
        code += f"d = d.groupby(['sigla', 'hora_observacao'], as_index=False)['{col}'].mean()\n"
        note += 'Duplicatas no mesmo instante são reduzidas à média dos valores válidos. '
    if full_hour:
        code += "d = d.loc[(d['hora_observacao'].dt.minute == 0) & (d['hora_observacao'].dt.second == 0)]\n"
        note += 'Somente boletins na hora cheia, evitando somar janelas horárias sobrepostas; lacunas não são preenchidas. '
    if col in ('visibpre', 'altnuvem'):
        code += f"d['{col}'] = d['{col}'] * 10\n"
        note += 'Dezenas de metros convertidas para metros. '
        if col == 'visibpre':
            note += 'O código 2000 é tratado como 20000 m, limite inferior censurado. '
    else:
        note += 'Unidades originais: °C para temperaturas, % para umidade, hPa para QNH, nós para vento, mm para chuva e minutos para duração. '
    if extra:
        setup, explanation = extra
        code += setup + '\n'
        note += explanation
    code += expression + '\n'
    QUESTIONS.append(dict(id=f'E{len(QUESTIONS)+1:02d}', category=category, question=question,
                          expected_behavior='answerable',
                          rationale='A estatística solicitada é calculável diretamente nos boletins da variável e do período indicados.',
                          assumptions=note.strip(), oracle_pandas=code))


def scalar(cat, text, station, start, end, col, op, **kwargs):
    add(cat, text, [station], start, end, col,
        f"result = [(float(d['{col}'].{op}()),)]" if op != 'count' else f"result = [(int(d['{col}'].count()),)]", **kwargs)


# 12 simples
scalar('simples', 'Qual foi a média do bulbo úmido em SBBQ em agosto de 2016?', 'SBBQ', '2016-08-01', '2016-09-01', 'bumido', 'mean')
scalar('simples', 'Até quanto chegou o ponto de orvalho em SBAT em fevereiro de 2017?', 'SBAT', '2017-02-01', '2017-03-01', 'temppo', 'max')
scalar('simples', 'Quero a menor pressão QNH registrada em SBCR no ano de 2018.', 'SBCR', '2018-01-01', '2019-01-01', 'qnh', 'min')
scalar('simples', 'Em setembro de 2019, qual foi a umidade relativa média de SBMK?', 'SBMK', '2019-09-01', '2019-10-01', 'ur', 'mean')
scalar('simples', 'Qual a menor visibilidade predominante, em metros, observada em SBJV em junho de 2020?', 'SBJV', '2020-06-01', '2020-07-01', 'visibpre', 'min')
scalar('simples', 'A maior rajada informada em SBYS ao longo de 2021 foi de quantos nós?', 'SBYS', '2021-01-01', '2022-01-01', 'rajada', 'max')
scalar('simples', 'Qual a menor altura de base de nuvem, em metros, registrada em SBJA em julho de 2022?', 'SBJA', '2022-07-01', '2022-08-01', 'altnuvem', 'min')
scalar('simples', 'Qual foi a maior duração de chuva em um boletim de SBIL em abril de 2023, em minutos?', 'SBIL', '2023-04-01', '2023-05-01', 'durpreci', 'max')
scalar('simples', 'Somando os boletins das horas cheias, quanta chuva SBPF registrou em maio de 2024?', 'SBPF', '2024-05-01', '2024-06-01', 'precip', 'sum', full_hour=True)
scalar('simples', 'Qual foi a velocidade média do vento em SBAC em novembro de 2025, em nós?', 'SBAC', '2025-11-01', '2025-12-01', 'velvento', 'mean')
scalar('simples', 'Quantos boletins com pressão QNH válida há para SBAU em março de 2018?', 'SBAU', '2018-03-01', '2018-04-01', 'qnh', 'count')
scalar('simples', 'Qual a temperatura do ar mínima de SBVG entre 10 e 20 de julho de 2023, incluindo os dois dias?', 'SBVG', '2023-07-10', '2023-07-21', 'bseco', 'min')

# 8 condições: contagens de boletins não equivalem a duração do fenômeno.
conditions = [
 ('Em quantos boletins de SBHT de 2016 a umidade relativa ficou abaixo de 40%?', 'SBHT', 2016, 'ur', '< 40'),
 ('Quantas observações de SBKG em 2017 tiveram bulbo úmido acima de 24 °C?', 'SBKG', 2017, 'bumido', '> 24'),
 ('Conte os boletins de SBME em 2018 com ponto de orvalho inferior a 10 °C.', 'SBME', 2018, 'temppo', '< 10'),
 ('Em 2019, quantas vezes SBPS informou visibilidade predominante menor que 1500 metros?', 'SBPS', 2019, 'visibpre', '< 1500'),
 ('Quantos boletins de SBUR em 2020 apresentaram vento acima de 18 nós em alguma cabeceira?', 'SBUR', 2020, 'velvento', '> 18'),
 ('Em quantas observações de SBCH em 2021 houve uma base de nuvem abaixo de 300 metros?', 'SBCH', 2021, 'altnuvem', '< 300'),
 ('Quantos boletins de SBBV em 2022 registraram chuva com duração maior que 30 minutos?', 'SBBV', 2022, 'durpreci', '> 30'),
]
for text, station, year, col, condition in conditions:
    add('condicao', text, [station], f'{year}-01-01', f'{year+1}-01-01', col,
        f"result = [(int((d['{col}'] {condition}).sum()),)]")
add('condicao', 'Em quantos dias de 2025 a máxima de temperatura do ar em SBDN ultrapassou 35 °C?', ['SBDN'], '2025-01-01', '2026-01-01', 'bseco',
    "daily = d.groupby(d['hora_observacao'].dt.date)['bseco'].max()\nresult = [(int((daily > 35).sum()),)]",
    extra=("", 'Dias locais com ao menos uma leitura válida; dias ausentes não contam.'))

# 8 séries e rankings
for text, station, year, col, op in [
 ('Como variou, mês a mês, o bulbo úmido médio de SBIZ em 2016?', 'SBIZ', 2016, 'bumido', 'mean'),
 ('Mostre a pressão QNH mínima de SBPP em cada mês de 2017.', 'SBPP', 2017, 'qnh', 'min'),
 ('Quais foram as médias mensais do ponto de orvalho de SBJU em 2018?', 'SBJU', 2018, 'temppo', 'mean'),
 ('Preciso da menor visibilidade predominante de SBCA por mês de 2019, em metros.', 'SBCA', 2019, 'visibpre', 'min'),
]:
    add('serie_ranking', text, [station], f'{year}-01-01', f'{year+1}-01-01', col,
        f"s = d.groupby(d['hora_observacao'].dt.month)['{col}'].{op}()\nresult = [(int(month), float(value)) for month, value in s.items()]",
        extra=('', 'Só meses com valores válidos aparecem, em ordem cronológica.'))
add('serie_ranking', 'De 2016 a 2025, qual foi a umidade relativa média de SBPL em cada ano?', ['SBPL'], '2016-01-01', '2026-01-01', 'ur',
    "s = d.groupby(d['hora_observacao'].dt.year)['ur'].mean()\nresult = [(int(year), float(value)) for year, value in s.items()]",
    extra=('', 'Somente anos com dados válidos, em ordem cronológica.'))
for text, year, col, op, ascending in [
 ('Quais foram as cinco estações com maior velocidade média do vento em 2020?', 2020, 'velvento', 'mean', False),
 ('Em 2023, quais cinco estações tiveram as menores médias de umidade relativa?', 2023, 'ur', 'mean', True),
 ('Qual estação apresentou o maior ponto de orvalho de 2024?', 2024, 'temppo', 'max', False),
]:
    n = 1 if year == 2024 else 5
    add('serie_ranking', text, None, f'{year}-01-01', f'{year+1}-01-01', col,
        f"s = d.groupby('sigla')['{col}'].{op}().reset_index(name='value')\ns = s.sort_values(['value', 'sigla'], ascending=[{ascending}, True]).head({n})\nresult = [(str(row.sigla), float(row.value)) for row in s.itertuples()]",
        extra=('', 'Universo: todas as siglas presentes no CSV com pelo menos um valor válido, inclusive identificadores especiais; sem limiar de cobertura. Empates ordenados por sigla.'))

# 4 comparações, uma resposta com dois valores identificados.
add('comparacao', 'Compare o bulbo úmido médio de SBMQ e SBRB em outubro de 2021.', ['SBMQ', 'SBRB'], '2021-10-01', '2021-11-01', 'bumido',
    "s = d.groupby('sigla')['bumido'].mean()\nresult = [(str(station), float(value)) for station, value in s.items()]")
add('comparacao', 'Como se comparam as mínimas de QNH de SBCO em julho de 2016 e julho de 2025?', ['SBCO'], '2016-01-01', '2026-01-01', 'qnh',
    "d = d.loc[(d['hora_observacao'].dt.month == 7) & d['hora_observacao'].dt.year.isin([2016, 2025])]\ns = d.groupby(d['hora_observacao'].dt.year)['qnh'].min()\nresult = [(int(year), float(value)) for year, value in s.items()]")
add('comparacao', 'Qual a velocidade média do vento de SBMS em relação à de SBFS em março de 2022?', ['SBMS', 'SBFS'], '2022-03-01', '2022-04-01', 'velvento',
    "s = d.groupby('sigla')['velvento'].mean()\nresult = [(str(station), float(value)) for station, value in s.items()]")
add('comparacao', 'Compare a umidade relativa média de SBMA no primeiro e no segundo semestre de 2024.', ['SBMA'], '2024-01-01', '2025-01-01', 'ur',
    "s = d.groupby(((d['hora_observacao'].dt.month - 1) // 6) + 1)['ur'].mean()\nresult = [(int(semester), float(value)) for semester, value in s.items()]")


def no_oracle(category, text, rationale):
    QUESTIONS.append(dict(id=f'E{len(QUESTIONS)+1:02d}', category=category, question=text,
                          expected_behavior='unsupported' if category == 'impossivel' else 'needs_clarification',
                          rationale=rationale, assumptions='nenhuma'))


for text, why in [
 ('Em qual cidade e estado fica a estação SBGM?', 'Os CSVs não contêm cadastro de cidades ou estados.'),
 ('Qual é a latitude da estação SBUA?', 'Não existe coluna de coordenadas geográficas.'),
 ('Que temperatura máxima SBTE terá em 15 de janeiro de 2027?', 'Os arquivos históricos não fornecem previsões meteorológicas.'),
 ('Qual foi a radiação solar média em SBPJ em agosto de 2020?', 'Radiação solar não é uma grandeza disponível.'),
 ('Qual a pressão QNH mínima de SBMN em dezembro de 2015?', 'O período solicitado antecede a cobertura dos arquivos.'),
 ('Qual foi a umidade relativa média da estação ZZQX em 2021?', 'ZZQX não consta da lista de estações extraída dos dados.'),
]:
    no_oracle('impossivel', text, why)
for text, why in [
 ('Qual foi o pior dia em SBLO em 2022?', 'É necessário definir qual grandeza e qual critério tornam um dia pior.'),
 ('Quanto choveu?', 'Faltam estação e período da consulta.'),
 ('Como estava a temperatura em SBBH em maio de 2021?', 'É necessário esclarecer a temperatura desejada e a estatística ou instante de interesse.'),
 ('Em SBMT, o vento estava forte naquela noite?', 'Faltam a data, o intervalo de noite e o critério para vento forte.'),
]:
    no_oracle('ambigua', text, why)

# 4 variações informais
scalar('informal', 'Me diz a menor temperatua do ar de SBTT em junho de 2017?', 'SBTT', '2017-06-01', '2017-07-01', 'bseco', 'min')
scalar('informal', 'em sbcz, qual foi a umidade relativa média em abril de 2019?', 'SBCZ', '2019-04-01', '2019-05-01', 'ur', 'mean')
scalar('informal', 'No dia 13 de março de 2021, qual foi o maior QNH de SBJP?', 'SBJP', '2021-03-13', '2021-03-14', 'qnh', 'max')
scalar('informal', 'De SBVH em agosto de 2025, manda a média do ponto de orvalho, por favor.', 'SBVH', '2025-08-01', '2025-09-01', 'temppo', 'mean')

# 4 recortes temporais: definições explícitas e verificáveis.
scalar('tempo', 'Qual foi a temperatura média do ar em SBJH de madrugada, entre 0h e antes das 6h, em janeiro de 2022?', 'SBJH', '2022-01-01', '2022-02-01', 'bseco', 'mean',
       extra=("d = d.loc[d['hora_observacao'].dt.hour < 6]", 'Madrugada definida na pergunta como [00:00, 06:00), na data local do boletim.'))
scalar('tempo', 'Durante a noite, das 18h às 6h, qual foi a umidade relativa média de SBNF em julho de 2020?', 'SBNF', '2020-07-01', '2020-08-01', 'ur', 'mean',
       extra=("h = d['hora_observacao'].dt.hour\nd = d.loc[(h >= 18) | (h < 6)]", 'Noite: [18:00, 24:00) ou [00:00, 06:00); julho pela data local de cada leitura.'))
scalar('tempo', 'Nos fins de semana de 2023, qual foi a pressão QNH média de SBBP?', 'SBBP', '2023-01-01', '2024-01-01', 'qnh', 'mean',
       extra=("d = d.loc[d['hora_observacao'].dt.dayofweek >= 5]", 'Fim de semana corresponde a sábado e domingo, pela data local.'))
scalar('tempo', 'Qual foi a média de bulbo úmido de SBZM no primeiro trimestre de 2018?', 'SBZM', '2018-01-01', '2018-04-01', 'bumido', 'mean',
       extra=('', 'Primeiro trimestre: janeiro, fevereiro e março completos.'))


if __name__ == '__main__':
    expected = dict(simples=12, condicao=8, serie_ranking=8, comparacao=4, impossivel=6, ambigua=4, informal=4, tempo=4)
    assert Counter(q['category'] for q in QUESTIONS) == expected
    assert len({q['question'] for q in QUESTIONS}) == 50
    stations = set(re.findall(r'\b(?:SB|SD|SS)[A-Z]{2}\b', ' '.join(q['question'].upper() for q in QUESTIONS)))
    assert len(stations) >= 25
    for q in QUESTIONS:
        if 'oracle_pandas' in q:
            compile(q['oracle_pandas'], q['id'], 'exec')
    class Dumper(yaml.SafeDumper):
        pass
    def represent_string(dumper, value):
        return dumper.represent_scalar('tag:yaml.org,2002:str', value, style='|' if '\n' in value else None)
    Dumper.add_representer(str, represent_string)
    with TARGET.open('x', encoding='utf-8', newline='\n') as f:
        yaml.dump({'questions': QUESTIONS}, f, Dumper=Dumper, allow_unicode=True, sort_keys=False, width=120)
    print(f'{TARGET.name}: 50 perguntas, {len(stations)} estações explícitas; 40 oráculos compilados.')
