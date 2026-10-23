from pathlib import Path
import ast,json,yaml,pandas as pd
W=Path(__file__).resolve().parent
qs=yaml.safe_load((W/'questions_independent_raw.yaml').read_bytes())['questions']
specs=[]
for q in qs:
    if 'oracle_pandas' not in q:continue
    tree=ast.parse(q['oracle_pandas'])
    spec={'id':q['id'],'raw_rows':0,'valid_rows':0,'valid_years':{},'hourly':'.dt.floor("h")' in q['oracle_pandas'],'ranges':{}}
    for n in tree.body:
        if isinstance(n,ast.Assign) and isinstance(n.targets[0],ast.Name):
            name=n.targets[0].id
            if name in ['columns','stations']:spec[name]=ast.literal_eval(n.value)
            if name=='path':spec['file']=ast.literal_eval(n.value.right)
    spec['dates']=[ast.literal_eval(n.args[0]) for n in ast.walk(tree) if isinstance(n,ast.Call) and ast.unparse(n.func)=='pd.Timestamp']
    for n in ast.walk(tree):
        if isinstance(n,ast.Call) and isinstance(n.func,ast.Attribute) and n.func.attr=='between':
            spec['ranges'][ast.literal_eval(n.func.value.slice)]=[ast.literal_eval(a) for a in n.args]
    assert len(spec['dates'])==2
    specs.append(spec)
root=Path(r'C:\Users\Gabriel\OneDrive\Área de Trabalho\Parente\METEOROLOGIA')
for filename in sorted({s['file'] for s in specs}):
    group=[s for s in specs if s['file']==filename]
    cols=sorted(set(c for s in group for c in s['columns']))
    for chunk in pd.read_csv(root/filename,usecols=cols,dtype=str,chunksize=200000):
        chunk['sigla']=chunk['sigla'].str.strip().str.upper()
        for s in group:
            d=chunk.loc[chunk['sigla'].isin(s['stations']) & chunk.hora_observacao.ge(s['dates'][0]) & chunk.hora_observacao.lt(s['dates'][1])]
            s['raw_rows']+=len(d)
            if d.empty:continue
            t=pd.to_datetime(d.hora_observacao,errors='coerce')
            mask=t.notna()
            if s['hourly']:mask &= t.eq(t.dt.floor('h'))
            if s['id']=='E48':mask &= t.dt.hour.lt(6)
            if s['id']=='E50':mask &= t.dt.dayofweek.ge(5)
            if s['id']=='E32':mask &= t.dt.month.isin([4,10])
            for c,(lo,hi) in s['ranges'].items():
                numeric=pd.to_numeric(d[c].str.strip().str.replace(',','.',regex=False),errors='coerce')
                mask &= numeric.between(lo,hi)
            s['valid_rows']+=int(mask.sum())
            for year,n in t[mask].dt.year.value_counts().items():s['valid_years'][str(year)]=s['valid_years'].get(str(year),0)+int(n)
    print(filename,[(s['id'],s['raw_rows'],s['valid_rows']) for s in group],flush=True)
(W/'input_coverage.json').write_text(json.dumps(specs,ensure_ascii=False,indent=2),encoding='utf-8')
