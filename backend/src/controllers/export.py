import csv,io
from fastapi import HTTPException
from fastapi.responses import Response
def export_review(obj):
    if obj.status not in ('completed','approved'):raise HTTPException(409,'计算完成后才可导出')
    output=io.StringIO();w=csv.writer(output)
    w.writerow(['复核单',obj.id,'标题',obj.title,'状态',obj.status,'范围',obj.line,'到货月份',getattr(obj,'month','全部') or '全部'])
    for k in ['n','mean','std','q1','median','q3','iqr','lower','upper','checksum']:w.writerow([k,obj.result[k]])
    w.writerow(['签核人',obj.approved_by,'签核意见',obj.note])
    w.writerow(['样本编号','批次','产线','到货日期','出粉率','水分','异常'])
    out={r['sample_code'] for r in obj.result['outliers']}
    for row in obj.snapshot:w.writerow([row['sample_code'],row['batch_code'],row['line'],row.get('received_date',''),row['flour_yield'],row['moisture'],'是' if row['sample_code'] in out else '否'])
    return Response('﻿'+output.getvalue(),media_type='text/csv; charset=utf-8',headers={'Content-Disposition':f'attachment; filename="mill-yield-review-{obj.id}.csv"'})
