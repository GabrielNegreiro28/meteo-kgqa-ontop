from pathlib import Path
from collections import Counter
import ast
import hashlib
import inspect
import textwrap
import yaml

OUT = Path(r'C:\Users\Gabriel\Documents\Codex\2026-10-23\files-pasted-by-the-user-markdown\work\questions_independent_raw.yaml')
ROOT = r'C:\Users\Gabriel\OneDrive\Área de Trabalho\Parente\METEOROLOGIA'
questions = []

def oracle(file, stations, start, end, specs, body, aggregation='mean', hourly=False, pre=''):
    cols = ['sigla', 'hora_observacao'] + list(specs)
    code = f'''import pandas as pd
from pathlib import Path

path = Path({ROOT!r}) / {file!r}
columns = {cols!r}
stations = {stations!r}
parts = []
for chunk in pd.read_csv(path, usecols=columns, dtype=str, sep=None,
                         engine="python", chunksize=50000):
    chunk["sigla"] = chunk["sigla"].str.strip().str.upper()
    chunk = chunk.loc[chunk["sigla"].isin(stations)].copy()
    chunk["hora_observacao"] = pd.to_datetime(chunk["hora_observacao"], errors="coerce")
    chunk = chunk.loc[chunk["hora_observacao"].ge(pd.Timestamp({start!r})) &
                      chunk["hora_observacao"].lt(pd.Timestamp({end!r}))]
    if not chunk.empty:
        parts.append(chunk)
d = pd.concat(parts, ignore_index=True) if parts else pd.DataFrame(columns=columns)
d["hora_observacao"] = pd.to_datetime(d["hora_observacao"], errors="coerce")
'''
    for field, (lo, hi, factor) in specs.items():
        code += f'd[{field!r}] = pd.to_numeric(d[{field!r}].astype("string").str.strip().str.replace(",", ".", regex=False), errors="coerce")\n'
        code += f'd[{field!r}] = d[{field!r}].where(d[{field!r}].between({lo}, {hi})).astype(float) * {factor}\n'
    if hourly:
        code += 'd = d.loc[d["hora_observacao"].eq(d["hora_observacao"].dt.floor("h"))].copy()\n'
    if pre:
        code += textwrap.dedent(pre).strip() + '\n'
    code += f'd = d.groupby(["sigla", "hora_observacao"], as_index=False)[{list(specs)!r}].{aggregation}()\n'
    code += 'def value(x):\n    return None if pd.isna(x) else float(x)\n'
    return code + inspect.cleandoc(body).strip() + '\n'

common = 'Horários em Brasília, UTC−3 fixo; datas incluem os dias indicados. Vazios, textos não numéricos e valores fora dos limites declarados são ausentes, nunca zero. '

def add(category, question, file, stations, start, end, specs, body, extra, aggregation='mean', hourly=False, pre=''):
    constraints = '; '.join(f'{name}: de {lo} a {hi}, inclusive, na unidade original' for name, (lo, hi, _) in specs.items())
    assumptions = common + 'Faixas aceitas: ' + constraints + '. ' + extra
    if aggregation == 'mean':
        assumptions += ' Duplicatas de estação e instante são consolidadas pela média de cada valor válido; cada instante tem peso igual.'
    elif aggregation == 'max':
        assumptions += ' Cabeceiras do mesmo instante são consolidadas pelo máximo válido; contam-se boletins distintos, não linhas de cabeceira.'
    elif aggregation == 'min':
        assumptions += ' As camadas de cada estação e instante são consolidadas pela menor base válida; cada boletim conta uma vez.'
    if hourly:
        assumptions += ' Usam-se somente instantes exatamente na hora cheia para não somar janelas horárias sobrepostas ou contar uma hora várias vezes.'
    questions.append(dict(id=f'E{len(questions)+1:02}', category=category, question=question,
        expected_behavior='answerable', rationale='A grandeza e o recorte solicitados estão disponíveis nos CSV e permitem cálculo direto.',
        assumptions=assumptions, oracle_pandas=oracle(file, stations, start, end, specs, body, aggregation, hourly, pre)))

T={'bseco':(-80,60,1)}
D={'temppo':(-100,60,1)}
U={'ur':(0,100,1)}
P={'qnh':(850,1100,1)}
V={'visibpre':(0,2000,10)}
R={'precip':(0,300,1)}
W={'velvento':(0,150,1)}
H={'altnuvem':(0,2500,10)}
C={'qtdnuvem':(0,8,1),'altnuvem':(0,2500,10)}
vis='Visibilidade multiplicada por 10 para obter metros; 2000 representa pelo menos 20000 m e é tratado como 20000 m, portanto médias ficam limitadas pelo teto de registro.'
rain='Chuva em mm; o total soma apenas medições válidas disponíveis, sem preencher lacunas. Sem nenhuma medição válida, o total é nulo.'
wind='Velocidade em nós, usando o maior vento entre as cabeceiras em cada boletim.'

add('simples','Qual foi a temperatura média do ar em SBAN em maio de 2016?', 'temperatura.csv',['SBAN'],'2016-05-01','2016-06-01',T,
    'result = [(value(d["bseco"].mean()),)]','Temperatura em °C.')
add('simples','A que temperatura chegou o dia mais quente de 2024 em SBAR?', 'temperatura.csv',['SBAR'],'2024-01-01','2025-01-01',T,
    'result = [(value(d["bseco"].max()),)]','Interpreta-se como a maior temperatura do ar observada, em °C, sem estimar extremos entre medições.')
add('simples','Quero o menor ponto de orvalho registrado em SBBI durante julho de 2019.', 'temperatura.csv',['SBBI'],'2019-07-01','2019-08-01',D,
    'result = [(value(d["temppo"].min()),)]','Ponto de orvalho em °C.')
add('simples','Em 2021, qual foi a umidade relativa média de SBBV?', 'temperatura.csv',['SBBV'],'2021-01-01','2022-01-01',U,
    'result = [(value(d["ur"].mean()),)]','Umidade relativa em %.')
add('simples','Preciso da média do QNH de SBCF entre 1º e 15 de setembro de 2022.', 'pressao.csv',['SBCF'],'2022-09-01','2022-09-16',P,
    'result = [(value(d["qnh"].mean()),)]','QNH em hPa.')
add('simples','Qual a menor visibilidade que apareceu em SBCG em agosto de 2020?', 'visibilidade.csv',['SBCG'],'2020-08-01','2020-09-01',V,
    'result = [(value(d["visibpre"].min()),)]',vis)
add('simples','Quanto choveu ao todo em SBCH em junho de 2023?', 'precipitacao.csv',['SBCH'],'2023-06-01','2023-07-01',R,
    'result = [(value(d["precip"].sum(min_count=1)),)]',rain,hourly=True)
add('simples','Qual foi a média da temperatura de bulbo úmido em SBEG no ano de 2025?', 'temperatura.csv',['SBEG'],'2025-01-01','2026-01-01',{'bumido':(-80,60,1)},
    'result = [(value(d["bumido"].mean()),)]','Bulbo úmido em °C.')
add('simples','Qual foi o vento mais forte medido em SBFZ em 2018, sem considerar rajadas?', 'vento.csv',['SBFZ'],'2018-01-01','2019-01-01',W,
    'result = [(value(d["velvento"].max()),)]',wind,aggregation='max')
add('simples','Quantas observações válidas de visibilidade há para SBGL em dezembro de 2017?', 'visibilidade.csv',['SBGL'],'2017-12-01','2018-01-01',V,
    'result = [(int(d["visibpre"].notna().sum()),)]',vis+' Uma observação é um instante distinto com valor válido.')
add('simples','Em SBGO, qual foi a altura média da camada mais baixa de nuvens em 2020?', 'nuvem.csv',['SBGO'],'2020-01-01','2021-01-01',H,
    'result = [(value(d["altnuvem"].mean()),)]','Altura multiplicada por 10, em metros. A média usa só boletins com base de nuvem válida; ausência de camada não significa altura zero.',aggregation='min')
add('simples','Em SBGR, qual foi a duração média da chuva por hora em abril de 2021?', 'precipitacao.csv',['SBGR'],'2021-04-01','2021-05-01',{'durpreci':(0,60,1)},
    'result = [(value(d["durpreci"].mean()),)]','Duração da chuva em minutos por hora; inclui durações zero registradas. Durações ausentes não entram na média.',hourly=True)

add('condicao','Quantas vezes a temperatura do ar passou de 35 °C em SBCY em 2023?', 'temperatura.csv',['SBCY'],'2023-01-01','2024-01-01',T,
    'result = [(int(d["bseco"].gt(35).sum()),)]','Conta instantes observados com temperatura estritamente maior que 35 °C; não episódios contínuos.')
add('condicao','Durante junho de 2022, quantas horas tiveram visibilidade abaixo de 1 km em SBCT?', 'visibilidade.csv',['SBCT'],'2022-06-01','2022-07-01',V,
    'result = [(int(d["visibpre"].lt(1000).sum()),)]',vis+' O limiar é estrito.',hourly=True)
add('condicao','Em quantos dias de janeiro de 2024 a máxima de SBFL ficou acima de 30 °C?', 'temperatura.csv',['SBFL'],'2024-01-01','2024-02-01',T,
    'daily = d.groupby(d["hora_observacao"].dt.date)["bseco"].max()\nresult = [(int(daily.gt(30).sum()),)]','Máxima diária da temperatura do ar observada, em °C; dias sem temperatura válida não satisfazem a condição.')
add('condicao','Houve quantos registros de umidade relativa inferior a 40% em SBJP no ano de 2019?', 'temperatura.csv',['SBJP'],'2019-01-01','2020-01-01',U,
    'result = [(int(d["ur"].lt(40).sum()),)]','Contam-se instantes com umidade válida estritamente inferior a 40%.')
add('condicao','Quantos boletins de SBKP trouxeram QNH abaixo de 1000 hPa em agosto de 2021?', 'pressao.csv',['SBKP'],'2021-08-01','2021-09-01',P,
    'result = [(int(d["qnh"].lt(1000).sum()),)]','QNH em hPa; cada instante válido abaixo do limiar conta um boletim.')
add('condicao','Em SBLO, quantas horas de 2020 acumularam pelo menos 10 mm de chuva?', 'precipitacao.csv',['SBLO'],'2020-01-01','2021-01-01',R,
    'result = [(int(d["precip"].ge(10).sum()),)]','Precipitação da última hora em mm; inclui exatamente 10 mm.',hourly=True)
add('condicao','Em quantas horas de 2025 o vento em SBMQ atingiu ou superou 20 nós?', 'vento.csv',['SBMQ'],'2025-01-01','2026-01-01',W,
    'result = [(int(d["velvento"].ge(20).sum()),)]',wind+' Inclui exatamente 20 nós.',aggregation='max',hourly=True)
add('condicao','Quantos boletins de SBPA em julho de 2024 tiveram alguma camada com cobertura de pelo menos 5 oitavos e base abaixo de 300 metros?', 'nuvem.csv',['SBPA'],'2024-07-01','2024-08-01',C,
    'result = [(int(d["altnuvem"].lt(300).sum()),)]','Bases multiplicadas por 10, em metros; só camadas com cobertura válida de 5 a 8 oitavos entram. Boletins sem camada válida correspondente não são contados.',aggregation='min',pre='d = d.loc[d["qtdnuvem"].ge(5) & d["altnuvem"].notna()].copy()')

add('serie_ranking','Pode mostrar a temperatura média do ar de SBMA mês a mês em 2022?', 'temperatura.csv',['SBMA'],'2022-01-01','2023-01-01',T,
    '''s = d.groupby(d["hora_observacao"].dt.to_period("M"))["bseco"].mean()
    s = s.reindex(pd.period_range("2022-01", "2022-12", freq="M"))
    result = [(str(month), value(v)) for month, v in s.items()]''','Temperatura em °C; saída cronológica (ano-mês, média), com nulo para mês sem valor válido.')
add('serie_ranking','Como variou o QNH médio anual de SBME de 2016 a 2025?', 'pressao.csv',['SBME'],'2016-01-01','2026-01-01',P,
    '''s = d.groupby(d["hora_observacao"].dt.year)["qnh"].mean().reindex(range(2016, 2026))
    result = [(int(year), value(v)) for year, v in s.items()]''','QNH em hPa; saída (ano, média), em ordem crescente de ano; anos sem valor válido ficam nulos.')
add('serie_ranking','Entre SBBE, SBEG, SBMN, SBRB, SBPV, SBSN, SBMQ e SBMA, quais foram as cinco estações com maior chuva acumulada em 2023?', 'precipitacao.csv',['SBBE','SBEG','SBMN','SBRB','SBPV','SBSN','SBMQ','SBMA'],'2023-01-01','2024-01-01',R,
    '''s = d.groupby("sigla")["precip"].sum(min_count=1).dropna().rename("total").reset_index()
    s = s.sort_values(["total", "sigla"], ascending=[False, True]).head(5)
    result = [(str(row.sigla), float(row.total)) for row in s.itertuples(index=False)]''',rain+' Ranking dos totais disponíveis, sem ajuste por cobertura; desempate pela sigla em ordem alfabética.',hourly=True)
add('serie_ranking','Em qual mês de 2020 SBMN teve a menor visibilidade média?', 'visibilidade.csv',['SBMN'],'2020-01-01','2021-01-01',V,
    '''s = d.groupby(d["hora_observacao"].dt.to_period("M"))["visibpre"].mean().dropna()
    result = [(str(month), float(v)) for month, v in s.items() if v == s.min()]''',vis+' Retorna todos os meses empatados na menor média, em ordem cronológica.')
add('serie_ranking','Qual estação registrou a maior temperatura do ar em 2024: SBCY, SBTE, SBPL, SBBV, SBPJ ou SBGO?', 'temperatura.csv',['SBCY','SBTE','SBPL','SBBV','SBPJ','SBGO'],'2024-01-01','2025-01-01',T,
    '''s = d.groupby("sigla")["bseco"].max().dropna()
    result = [(str(station), float(v)) for station, v in s.items() if v == s.max()]''','Máximo observado em °C. Retorna todas as estações empatadas no maior valor, em ordem alfabética.')
add('serie_ranking','Liste a umidade relativa média de SBMO para cada ano de 2020 a 2025.', 'temperatura.csv',['SBMO'],'2020-01-01','2026-01-01',U,
    '''s = d.groupby(d["hora_observacao"].dt.year)["ur"].mean().reindex(range(2020, 2026))
    result = [(int(year), value(v)) for year, v in s.items()]''','Umidade em %; saída anual cronológica; ano sem dado válido tem média nula.')
add('serie_ranking','De 2018 a 2025, quantos boletins por ano de SBNF registraram uma base de nuvem abaixo de 200 metros?', 'nuvem.csv',['SBNF'],'2018-01-01','2026-01-01',H,
    '''low = d.loc[d["altnuvem"].lt(200)]
    s = low.groupby(low["hora_observacao"].dt.year).size().reindex(range(2018, 2026), fill_value=0)
    result = [(int(year), int(n)) for year, n in s.items()]''','Altura em metros após multiplicar por 10. Conta qualquer camada com base válida inferior a 200 m, sem exigência de cobertura; zero significa nenhum boletim observado que satisfaça o critério.',aggregation='min')
add('serie_ranking','Quero a mediana da velocidade do vento de SBRF em cada mês de 2021.', 'vento.csv',['SBRF'],'2021-01-01','2022-01-01',W,
    '''s = d.groupby(d["hora_observacao"].dt.to_period("M"))["velvento"].median()
    s = s.reindex(pd.period_range("2021-01", "2021-12", freq="M"))
    result = [(str(month), value(v)) for month, v in s.items()]''',wind+' Medianas mensais em ordem cronológica; mês sem dado válido tem valor nulo.',aggregation='max')

add('comparacao','SBNT ou SBSG teve a maior temperatura média do ar em 2020? Mostre as duas médias.', 'temperatura.csv',['SBNT','SBSG'],'2020-01-01','2021-01-01',T,
    '''s = d.groupby("sigla")["bseco"].mean().reindex(["SBNT", "SBSG"])
    result = [(station, value(v)) for station, v in s.items()]''','Médias em °C, calculadas com os registros válidos de cada estação, sem restringir aos horários comuns. As duas médias determinam o maior valor ou empate.')
add('comparacao','Quanto mudou o QNH médio de SBRJ de 2022 para 2023?', 'pressao.csv',['SBRJ'],'2022-01-01','2024-01-01',P,
    '''s = d.groupby(d["hora_observacao"].dt.year)["qnh"].mean().reindex([2022, 2023])
    result = [(value(s.loc[2022]), value(s.loc[2023]), value(s.loc[2023] - s.loc[2022]))]''','QNH em hPa; saída (média de 2022, média de 2023, diferença 2023 menos 2022). Sem dados para um ano, sua média e a diferença são nulas.')
add('comparacao','Quem acumulou mais chuva em outubro de 2024, SBRB ou SBPV, e qual foi a diferença?', 'precipitacao.csv',['SBRB','SBPV'],'2024-10-01','2024-11-01',R,
    '''s = d.groupby("sigla")["precip"].sum(min_count=1).reindex(["SBRB", "SBPV"])
    a, b = s.loc["SBRB"], s.loc["SBPV"]
    winner = None if pd.isna(a) or pd.isna(b) else ("empate" if a == b else ("SBRB" if a > b else "SBPV"))
    result = [(value(a), value(b), winner, value(abs(a-b)))]''',rain+' Compara totais disponíveis, sem normalização por cobertura; saída (total SBRB, total SBPV, estação com maior total ou empate, diferença absoluta).',hourly=True)
add('comparacao','A mediana da visibilidade em SBSC foi maior em abril ou em outubro de 2021?', 'visibilidade.csv',['SBSC'],'2021-04-01','2021-11-01',V,
    '''d = d.loc[d["hora_observacao"].dt.month.isin([4, 10])]
    s = d.groupby(d["hora_observacao"].dt.month)["visibpre"].median().reindex([4, 10])
    result = [("2021-04", value(s.loc[4])), ("2021-10", value(s.loc[10]))]''',vis+' Saída com as duas medianas em metros; igualdade é empate, e mês sem dados é nulo.')

def special(category, question, rationale):
    questions.append(dict(id=f'E{len(questions)+1:02}', category=category, question=question,
        expected_behavior='unsupported' if category=='impossivel' else 'needs_clarification',
        rationale=rationale, assumptions='nenhuma'))

special('impossivel','Em qual cidade e estado fica a estação SBSP?', 'Os CSV não contêm cadastro de cidades ou estados associado às siglas.')
special('impossivel','Qual é a latitude de SBRP?', 'Não há coordenadas geográficas nos arquivos disponíveis.')
special('impossivel','Vai chover em SBVT no dia 10 de janeiro de 2027?', 'Há apenas observações históricas até 2025, sem previsão meteorológica para 2027.')
special('impossivel','Qual foi a radiação solar média diária de SBTE em 2020?', 'Nenhum dos arquivos contém medidas de radiação solar.')
special('impossivel','Quanto choveu em SBUL durante 2015?', 'O ano de 2015 está fora da cobertura temporal de todos os arquivos.')
special('impossivel','Qual foi a temperatura média do ar na estação SBZZ em 2024?', 'SBZZ não está na lista de estações fornecida.')
special('ambigua','Qual foi o pior dia de 2023 em SBPS?', 'É necessário esclarecer qual grandeza ou critério define o pior dia.')
special('ambigua','Está quente em SBPL?', 'Faltam o instante ou período de interesse e o critério de referência para considerar quente.')
special('ambigua','Me passa a média da umidade relativa de julho.', 'Não foram informados a estação nem o ano de julho a analisar.')
special('ambigua','Qual foi a direção predominante em SBRF em setembro de 2022?', 'É necessário esclarecer se a direção solicitada é a do vento ou a das nuvens.')

add('informal','qual foi a média da temperat ua do ar em sbsv no dia 13 de março de 2021?', 'temperatura.csv',['SBSV'],'2021-03-13','2021-03-14',T,
    'result = [(value(d["bseco"].mean()),)]','Interpreta-se o erro de digitação como temperatura; sigla normalizada para SBSV; resultado em °C.')
add('informal','em sbsl, o vento bateu quantos nós no máximo em 2022? sem contar rajada', 'vento.csv',['SBSL'],'2022-01-01','2023-01-01',W,
    'result = [(value(d["velvento"].max()),)]',wind+' Sigla em minúsculas interpretada como SBSL.',aggregation='max')
add('informal','De julho de 2020 em SBTG, me diz o menor ponto de orvalho que teve.', 'temperatura.csv',['SBTG'],'2020-07-01','2020-08-01',D,
    'result = [(value(d["temppo"].min()),)]','Ponto de orvalho em °C, mínimo das observações válidas do mês.')
add('informal','E aí, quanto de chuva juntou em sbug em junho de 2018?', 'precipitacao.csv',['SBUG'],'2018-06-01','2018-07-01',R,
    'result = [(value(d["precip"].sum(min_count=1)),)]',rain+' Sigla em minúsculas interpretada como SBUG.',hourly=True)

add('tempo','Qual foi a temperatura média do ar em SBBR no verão de 2022, considerando dezembro de 2021 a fevereiro de 2022?', 'temperatura.csv',['SBBR'],'2021-12-01','2022-03-01',T,
    'result = [(value(d["bseco"].mean()),)]','Verão definido na pergunta como os três meses completos de dezembro de 2021 a fevereiro de 2022; temperatura em °C.')
add('tempo','Em SBJV, qual foi a visibilidade média de madrugada, entre meia-noite e antes das seis, ao longo de 2023?', 'visibilidade.csv',['SBJV'],'2023-01-01','2024-01-01',V,
    'd = d.loc[d["hora_observacao"].dt.hour.lt(6)]\nresult = [(value(d["visibpre"].mean()),)]',vis+' Madrugada é o intervalo diário 00:00 inclusive a 06:00 exclusivo, no horário local fixo de Brasília.')
add('tempo','No primeiro trimestre de 2019, qual foi a maior temperatura do ar registrada em SBTB?', 'temperatura.csv',['SBTB'],'2019-01-01','2019-04-01',T,
    'result = [(value(d["bseco"].max()),)]','Primeiro trimestre inclui janeiro, fevereiro e março completos; máximo em °C.')
add('tempo','Qual foi a umidade relativa média em SBUA só nos fins de semana de 2024?', 'temperatura.csv',['SBUA'],'2024-01-01','2025-01-01',U,
    'd = d.loc[d["hora_observacao"].dt.dayofweek.ge(5)]\nresult = [(value(d["ur"].mean()),)]','Fim de semana corresponde a sábado e domingo no horário local fixo de Brasília; média em %, com cada instante observado tendo o mesmo peso.')

assert len(questions) == 50
assert Counter(q['category'] for q in questions) == dict(simples=12, condicao=8, serie_ranking=8, comparacao=4, impossivel=6, ambigua=4, informal=4, tempo=4)
assert len({q['question'] for q in questions}) == 50
for q in questions:
    if q['expected_behavior'] == 'answerable':
        ast.parse(q['oracle_pandas'])
    else:
        assert 'oracle_pandas' not in q

class Dumper(yaml.SafeDumper):
    pass
def represent_str(dumper, data):
    return dumper.represent_scalar('tag:yaml.org,2002:str', data, style='|' if '\n' in data else None)
Dumper.add_representer(str, represent_str)
OUT.write_text(yaml.dump({'questions':questions}, Dumper=Dumper, allow_unicode=True, sort_keys=False, width=120), encoding='utf-8')
parsed = yaml.safe_load(OUT.read_text(encoding='utf-8'))
assert parsed == {'questions':questions}
print(str(OUT))
print(hashlib.sha256(OUT.read_bytes()).hexdigest())
