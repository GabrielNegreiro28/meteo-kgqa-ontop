"""Execute one reviewed oracle in a fresh process; this is process isolation, not a security sandbox."""
import sys, json, math, traceback
from pathlib import Path
import pandas as pd
import numpy as np
import yaml
ALLOWED={
 'temperatura.csv':{'sigla','hora_observacao','bseco','bumido','ur','temppo','temppista'},
 'pressao.csv':{'sigla','hora_observacao','qnh'},
 'visibilidade.csv':{'sigla','hora_observacao','visibpre'},
 'precipitacao.csv':{'sigla','hora_observacao','precip','durpreci'},
 'vento.csv':{'sigla','hora_observacao','cabeceira','velvento','dirvento','rajada'},
 'nuvem.csv':{'sigla','hora_observacao','camada','qtdnuvem','altnuvem','tipo_nuvem','direcao_nuvem'},
}
BASE=Path(r'C:\Users\Gabriel\OneDrive\Área de Trabalho\Parente\METEOROLOGIA').resolve()
raw,qid,out=sys.argv[1:]
q=next(q for q in yaml.safe_load(Path(raw).read_text(encoding='utf-8'))['questions'] if q['id']==qid)
reads=[]
original_read_csv=pd.read_csv
def checked_read_csv(path,*args,**kwargs):
    p=Path(path).resolve()
    if p.parent!=BASE or p.name not in ALLOWED:raise ValueError('Unexpected CSV source')
    cols=kwargs.get('usecols')
    if not isinstance(cols,(list,tuple,set)) or not set(cols)<=ALLOWED[p.name]:raise ValueError('usecols must be explicit and permitted')
    reads.append({'file':p.name,'usecols':list(cols),'chunksize':kwargs.get('chunksize')})
    return original_read_csv(path,*args,**kwargs)
pd.read_csv=checked_read_csv

def scalar(v):
    if isinstance(v,np.generic):v=v.item()
    if v is None or (isinstance(v,float) and not math.isfinite(v)):raise ValueError('empty/nonfinite result cell')
    if isinstance(v,(pd.Timestamp,)):return v.isoformat()
    if not isinstance(v,(str,int,float,bool)):raise ValueError('unexpected result cell type '+type(v).__name__)
    return v
try:
    ns={'__name__':'__oracle__'}
    exec(compile(q['oracle_pandas'],qid,'exec'),ns)
    result=ns.get('result')
    if not isinstance(result,list) or not result:raise ValueError('result is not a nonempty list')
    if not all(isinstance(row,tuple) and row for row in result):raise ValueError('result rows must be nonempty tuples')
    if not reads:raise ValueError('oracle read no original CSV')
    obj={'id':qid,'status':'ok','result':[[scalar(v) for v in row] for row in result],'reads':reads}
except Exception as e:
    obj={'id':qid,'status':'error','error':type(e).__name__+': '+str(e),'traceback':traceback.format_exc(),'reads':reads}
Path(out).write_text(json.dumps(obj,ensure_ascii=False,indent=2,allow_nan=False),encoding='utf-8')
