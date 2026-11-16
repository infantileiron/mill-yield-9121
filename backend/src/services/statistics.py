import math,statistics,hashlib,json
from collections import Counter
def quantile(values,p):
    pos=(len(values)-1)*p
    lower=math.floor(pos);upper=math.ceil(pos)
    return values[lower]+(values[upper]-values[lower])*(pos-lower)
def diagnose(rows):
    if len(rows)<5: raise ValueError('至少需要 5 条有效检验记录')
    vals=sorted(float(x['flour_yield']) for x in rows)
    q1,median,q3=[quantile(vals,p) for p in (.25,.5,.75)]
    iqr=q3-q1;low,high=q1-1.5*iqr,q3+1.5*iqr
    edges=list(range(0,101,5))
    counts=[sum(a<=v<(b if b<100 else 101) for v in vals) for a,b in zip(edges,edges[1:])]
    groups={}
    for line in sorted(set(x['line'] for x in rows)):
        group=[x['flour_yield'] for x in rows if x['line']==line]
        groups[line]={'n':len(group),'mean':round(statistics.mean(group),4),'min':min(group),'max':max(group)}
    out=[x for x in rows if x['flour_yield']<low or x['flour_yield']>high]
    return dict(n=len(vals),mean=round(statistics.mean(vals),4),std=round(statistics.stdev(vals),4),min=min(vals),max=max(vals),q1=q1,median=median,q3=q3,iqr=iqr,lower=low,upper=high,outliers=out,histogram=[{'from':a,'to':b,'count':n} for a,b,n in zip(edges,edges[1:],counts)],groups=groups,checksum=hashlib.sha256(json.dumps(rows,sort_keys=True,ensure_ascii=False).encode()).hexdigest(),method='线性插值分位数；异常值严格落在 Q1−1.5×IQR / Q3+1.5×IQR 外；所有有效样本均纳入，不删除异常点。')
