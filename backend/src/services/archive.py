"""按到货月份归档 / 恢复原粮检验样本。

设计要点：
- 以“批”为最小迁移单元，每批在同一事务内完成「写入归档 → 逐条内容校验 → 删除在线行」，
  中断只会停在批边界，不会出现半批数据。
- 归档表 sample_code 唯一；写入前按 sample_code 判重，重试不会重复写入。
- 读取采用一次性 UNION ALL 查询并按 sample_code 去重，同一份样本只计一次；
  迁移/恢复过程中样本要么在在线表、要么在归档表，不会丢。
- 归档内容（逐行 SHA-256 + 整月校验和 + 样本数）在用于诊断/报告查证前校验；
  缺失或损坏时阻止使用并明确报出月份，绝不静默少算。
"""
import hashlib,json
from datetime import datetime,timezone
from sqlalchemy import select,func,literal,union_all,text,cast,Integer,Boolean,delete
from fastapi import HTTPException
from src.models.entities import Batch,Inspection,Archive,ArchivedInspection
from src.config.settings import REDIS_URL
from redis import Redis

queue=Redis.from_url(REDIS_URL,decode_responses=True)
ARCHIVE_QUEUE='mill:archive-jobs'
BUSY_STATES=('pending','migrating','restoring')

def now():return datetime.now(timezone.utc)
def month_of(received_date):return (received_date or '')[:7]

# ---------- 校验和 ----------
def _row_payload(row):
    return {'sample_code':row['sample_code'],'batch_id':row['batch_id'],'batch_code':row['batch_code'],
            'line':row['line'],'received_date':row['received_date'],'flour_yield':row['flour_yield'],
            'moisture':row['moisture'],'inspector':row['inspector']}
def row_checksum(row):
    return hashlib.sha256(json.dumps(_row_payload(row),sort_keys=True,ensure_ascii=False,separators=(',',':')).encode()).hexdigest()
def entity_row_checksum(r):
    return row_checksum({'sample_code':r.sample_code,'batch_id':r.batch_id,'batch_code':r.batch_code,'line':r.line,
                         'received_date':r.received_date,'flour_yield':r.flour_yield,'moisture':r.moisture,'inspector':r.inspector})
def archive_checksum(checksums):
    return hashlib.sha256('\n'.join(sorted(checksums)).encode()).hexdigest()

# ---------- 统一数据视图 ----------
def _online_query(month=None):
    q=select(Inspection.id.label('id'),Inspection.sample_code.label('sample_code'),Inspection.batch_id.label('batch_id'),
             Inspection.flour_yield.label('flour_yield'),Inspection.moisture.label('moisture'),Inspection.inspector.label('inspector'),
             Batch.code.label('batch_code'),Batch.line.label('line'),Batch.received_date.label('received_date'),
             cast(literal(None),Integer).label('origin_id'),literal(False).label('archived')).join(Batch,Batch.id==Inspection.batch_id)
    if month:q=q.where(func.substr(Batch.received_date,1,7)==month)
    return q
def _archived_query(month=None):
    q=select(ArchivedInspection.origin_id.label('id'),ArchivedInspection.sample_code.label('sample_code'),
             ArchivedInspection.batch_id.label('batch_id'),ArchivedInspection.flour_yield.label('flour_yield'),
             ArchivedInspection.moisture.label('moisture'),ArchivedInspection.inspector.label('inspector'),
             ArchivedInspection.batch_code.label('batch_code'),ArchivedInspection.line.label('line'),
             ArchivedInspection.received_date.label('received_date'),ArchivedInspection.origin_id.label('origin_id'),
             cast(literal(True),Boolean).label('archived'))
    if month:q=q.where(ArchivedInspection.month==month)
    return q

def samples_view(db,month=None):
    """单条 SQL 取在线 + 归档的完整快照；按 sample_code 去重，在线优先。"""
    sub=union_all(_online_query(month),_archived_query(month)).subquery()
    rows=db.execute(select(sub).order_by(sub.c.archived.asc())).mappings().all()
    distinct={}
    for r in rows:
        code=r['sample_code']
        if code in distinct:continue
        distinct[code]=dict(sample_code=code,batch_id=r['batch_id'],batch_code=r['batch_code'],line=r['line'],
                            received_date=r['received_date'],month=month_of(r['received_date']),
                            flour_yield=r['flour_yield'],moisture=r['moisture'],inspector=r['inspector'],
                            archived=bool(r['archived']),id=r['origin_id'] if r['archived'] else r['id'],
                            batch_seq=r['batch_id'] if r['archived'] else r['id'])
    return sorted(distinct.values(),key=lambda x:x['batch_seq'],reverse=True)

def batch_counts(db):
    sub=union_all(select(Inspection.batch_id.label('batch_id'),Inspection.sample_code.label('sample_code')),
                  select(ArchivedInspection.batch_id.label('batch_id'),ArchivedInspection.sample_code.label('sample_code'))).subquery()
    rows=db.execute(select(sub.c.batch_id,func.count(func.distinct(sub.c.sample_code))).group_by(sub.c.batch_id)).all()
    return {bid:n for bid,n in rows}

def month_online_counts(db):
    rows=db.execute(select(func.substr(Batch.received_date,1,7).label('m'),func.count(func.distinct(Inspection.sample_code)))
                    .join(Batch,Batch.id==Inspection.batch_id).group_by('m')).all()
    return {m:n for m,n in rows}

# ---------- 完整性校验 ----------
def _archived_rows(db,month):
    return db.scalars(select(ArchivedInspection).where(ArchivedInspection.month==month).order_by(ArchivedInspection.sample_code)).all()

def verify_month(db,month,persist=True):
    """返回归档完整性。发现缺失/损坏时持久化 corrupt 状态并带出月份。"""
    a=db.scalar(select(Archive).where(Archive.month==month))
    rows=_archived_rows(db,month)
    online=db.scalar(select(func.count(func.distinct(Inspection.sample_code))).join(Batch,Batch.id==Inspection.batch_id)
                     .where(func.substr(Batch.received_date,1,7)==month)) or 0
    out={'month':month,'exists':bool(a),'status':a.status if a else 'online','archived':len(rows),
         'online':online,'expected':a.archived_samples if a else 0,'checksum':'','problems':[],'ok':True}
    if not a:
        return out
    problems=out['problems']
    bad=[r.sample_code for r in rows if r.row_checksum!=entity_row_checksum(r)]
    if bad:
        problems.append(f"{len(bad)} 条归档样本内容校验不符：{', '.join(bad[:5])}{' 等' if len(bad)>5 else ''}")
    codes=[r.sample_code for r in rows]
    if len(codes)!=len(set(codes)):problems.append('归档表存在重复样本编号')
    if a.status in ('ready','failed','corrupt') and a.archived_samples!=len(rows):
        problems.append(f'归档样本缺失或多余：登记 {a.archived_samples} 条，实际 {len(rows)} 条')
    if a.checksum and a.status=='ready':
        computed=archive_checksum([r.row_checksum for r in rows])
        out['checksum']=computed
        if computed!=a.checksum:problems.append('整月归档校验和不一致，归档可能已损坏')
    if a.status=='restored' and len(rows):
        problems.append('已恢复月份仍残留归档样本')
    if problems:
        out['ok']=False
        if persist and a.status!='corrupt':
            a.status='corrupt';a.error='；'.join(problems);a.updated_at=now();db.commit()
    return out

def _months_in_play(db):
    months=set(db.scalars(select(Batch.received_date)).all())
    months={month_of(x) for x in months if x}
    months|={m for m in db.scalars(select(Archive.month)).all() if m}
    return sorted(months)

def ensure_readable(db,month_filter='全部'):
    """诊断/查证前调用：任何参与范围的归档损坏都必须阻止并指出月份。"""
    months=[month_filter] if month_filter and month_filter!='全部' else _months_in_play(db)
    for m in months:
        v=verify_month(db,m)
        if not v['ok']:
            raise HTTPException(409,f"归档 {m} 已损坏或缺失，已阻止本次分析以免少算；请先恢复或修复该月归档。")
    return months

# ---------- 月份汇总 ----------
def _archive_progress(a,batch_codes=None):
    items=a.batches or []
    done=[x for x in items if x.get('state') in ('archived','restored')]
    total=max(len(items),len(batch_codes or []))
    return {'total_batches':total,'done_batches':len(done),'batches':items}

def archive_list(db):
    online=month_online_counts(db)
    archived=dict(db.execute(select(ArchivedInspection.month,func.count()).group_by(ArchivedInspection.month)).all())
    batches_by_month={}
    for b in db.scalars(select(Batch).order_by(Batch.code)):
        batches_by_month.setdefault(month_of(b.received_date),set()).add(b.code)
    records={a.month:a for a in db.scalars(select(Archive).order_by(Archive.month.desc()))}
    out=[]
    for m in sorted(set(online)|set(archived)|set(records),reverse=True):
        a=records.get(m)
        status=a.status if a else ('ready' if archived.get(m,0) and not online.get(m,0) else 'online')
        item={'month':m,'status':status,'online_samples':online.get(m,0),'archived_samples':archived.get(m,0),
              'total_samples':online.get(m,0)+archived.get(m,0),'batch_codes':sorted(batches_by_month.get(m,set())),
              'error':a.error if a else '','checksum':a.checksum if a else '',
              'updated_at':a.updated_at.isoformat() if a and a.updated_at else '',
              'progress':_archive_progress(a,batches_by_month.get(m,set())) if a else {'total_batches':len(batches_by_month.get(m,set())),'done_batches':0,'batches':[]}}
        if a:
            # 轻量完整性判断，避免列表页逐行重算
            if a.status in ('ready','failed','corrupt') and a.archived_samples!=archived.get(m,0):item['status']='corrupt'
            if a.status in ('ready','restored','failed') and online.get(m,0)>0:item['new_samples']=online.get(m,0)
        out.append(item)
    return out

def month_detail(db,month):
    if month not in _months_in_play(db):raise HTTPException(404,'该到货月份没有批次记录')
    a=db.scalar(select(Archive).where(Archive.month==month))
    v=verify_month(db,month,persist=True)
    online_rows=db.execute(select(Inspection,Batch).join(Batch,Batch.id==Inspection.batch_id)
                           .where(func.substr(Batch.received_date,1,7)==month)).all()
    arch_rows=_archived_rows(db,month)
    per={}
    for b in db.scalars(select(Batch).where(func.substr(Batch.received_date,1,7)==month)):
        per[b.code]={'batch_code':b.code,'line':b.line,'supplier':b.supplier,'received_date':b.received_date,
                     'online':0,'archived':0,'state':'pending'}
    for i,b in online_rows:
        if b.code in per:per[b.code]['online']+=1
    for r in arch_rows:
        if r.batch_code in per:per[r.batch_code]['archived']+=1
        else:per[r.batch_code]={'batch_code':r.batch_code,'line':r.line,'supplier':'','received_date':r.received_date,
                                'online':0,'archived':0,'state':'archived'}
    for x in per.values():
        if x['online'] and x['archived']:x['state']='mixed'
        elif x['archived']:x['state']='archived'
        elif x['online']:x['state']='online'
    progress=_archive_progress(a,per.keys()) if a else {'total_batches':len(per),'done_batches':0,'batches':[]}
    return {'month':month,'status':a.status if a else 'online','operation':a.operation if a else '',
            'online_samples':len(online_rows),'archived_samples':len(arch_rows),
            'total_samples':v['online']+v['archived'],'expected_samples':a.archived_samples if a else 0,
            'checksum':a.checksum if a else '','error':a.error if a else '','verify':v,
            'progress':progress,'batches':sorted(per.values(),key=lambda x:x['batch_code'])}

# ---------- 迁移 / 恢复 ----------
def _advisory_lock(db,key):
    if db.bind.dialect.name!='postgresql':return True
    return bool(db.execute(text('SELECT pg_try_advisory_lock(hashtext(:k))'),{'k':key}).scalar())
def _advisory_unlock(db,key):
    if db.bind.dialect.name=='postgresql':
        try:db.execute(text('SELECT pg_advisory_unlock(hashtext(:k))'),{'k':key});db.commit()
        except Exception:db.rollback()

def _set_progress(a,code,state,samples):
    items=[x for x in (a.batches or []) if x.get('batch_code')!=code]
    items.append({'batch_code':code,'state':state,'samples':samples,'at':now().isoformat()})
    a.batches=sorted(items,key=lambda x:x['batch_code'])
    a.updated_at=now()

def _archive_one_batch(db,a,batch):
    rows=db.execute(select(Inspection).where(Inspection.batch_id==batch.id)).scalars().all()
    if not rows:
        _set_progress(a,batch.code,'archived',0);db.commit();return 0
    payloads=[{'sample_code':i.sample_code,'batch_id':batch.id,'batch_code':batch.code,'line':batch.line,
               'received_date':batch.received_date,'flour_yield':i.flour_yield,'moisture':i.moisture,
               'inspector':i.inspector} for i in rows]
    existing=set(db.scalars(select(ArchivedInspection.sample_code).where(
        ArchivedInspection.sample_code.in_([p['sample_code'] for p in payloads]))).all())
    for p in payloads:
        if p['sample_code'] in existing:continue
        db.add(ArchivedInspection(archive_id=a.id,month=a.month,origin_id=next(i.id for i in rows if i.sample_code==p['sample_code']),
                                  row_checksum=row_checksum(p),**p))
    db.flush()
    # 逐条内容校验：刚写入的归档行必须与在线行完全一致
    stored={r.sample_code:r for r in db.scalars(select(ArchivedInspection).where(
        ArchivedInspection.sample_code.in_([p['sample_code'] for p in payloads]))).all()}
    for p in payloads:
        r=stored.get(p['sample_code'])
        if not r or r.row_checksum!=row_checksum(p) or entity_row_checksum(r)!=row_checksum(p):
            raise RuntimeError(f"批次 {batch.code} 归档校验失败：样本 {p['sample_code']} 内容不一致，已回滚该批")
        if r.month!=a.month:
            raise RuntimeError(f"批次 {batch.code} 样本 {p['sample_code']} 已归入 {r.month}，月份归属冲突，已回滚该批")
    if len(stored)<len(payloads):raise RuntimeError(f'批次 {batch.code} 归档样本数不足，已回滚该批')
    # 校验通过后才移出在线区（按 id 精确删除，迁移期间新增行不受影响）
    db.execute(delete(Inspection).where(Inspection.id.in_([i.id for i in rows])))
    a.archived_samples=int(db.scalar(select(func.count()).select_from(ArchivedInspection).where(ArchivedInspection.month==a.month)) or 0)
    _set_progress(a,batch.code,'archived',len(payloads))
    db.commit()
    return len(payloads)

def run_archive(db,archive_id):
    key=f'mill:archive:{archive_id}'
    if not _advisory_lock(db,key):return
    try:
        a=db.get(Archive,archive_id)
        # 只处理仍处于待迁移/迁移中的存档；完成或已恢复后的陈旧队列项不再改状态
        if not a or a.operation!='archive' or a.status not in ('pending','migrating'):return
        a.status='migrating';a.error='';a.updated_at=now();db.commit()
        rounds=0
        while True:
            rounds+=1
            if rounds>20:break
            pending=db.execute(select(Batch).join(Inspection,Inspection.batch_id==Batch.id)
                               .where(func.substr(Batch.received_date,1,7)==a.month)
                               .group_by(Batch.id).order_by(Batch.id)).scalars().all()
            if not pending:break
            for batch in pending:
                # 幂等：状态已不合法说明别的任务先完成/被取消
                db.refresh(a)
                if a.status!='migrating':return
                _archive_one_batch(db,a,batch)
        rows=_archived_rows(db,a.month)
        a.archived_samples=len(rows)
        a.checksum=archive_checksum([r.row_checksum for r in rows])
        a.status='ready';a.error='';a.completed_at=now();a.updated_at=now();db.commit()
    except Exception as e:
        db.rollback()
        a=db.get(Archive,archive_id)
        if a:
            a.status='failed';a.error=str(e);a.updated_at=now();db.commit()
    finally:
        _advisory_unlock(db,key)

def _restore_one_batch(db,a,batch_code):
    rows=db.scalars(select(ArchivedInspection).where(ArchivedInspection.month==a.month,
                                                    ArchivedInspection.batch_code==batch_code)).all()
    if not rows:
        _set_progress(a,batch_code,'restored',0);db.commit();return 0
    # 恢复前再验一次内容，坏归档绝不写回在线区
    for r in rows:
        if r.row_checksum!=entity_row_checksum(r):raise RuntimeError(f'归档 {a.month} 样本 {r.sample_code} 校验失败，已阻止恢复')
    existing=set(db.scalars(select(Inspection.sample_code).where(
        Inspection.sample_code.in_([r.sample_code for r in rows]))).all())
    for r in rows:
        if r.sample_code in existing:continue
        db.add(Inspection(sample_code=r.sample_code,batch_id=r.batch_id,flour_yield=r.flour_yield,
                          moisture=r.moisture,inspector=r.inspector))
    db.flush()
    online=set(db.scalars(select(Inspection.sample_code).where(
        Inspection.sample_code.in_([r.sample_code for r in rows]))).all())
    missing=[r.sample_code for r in rows if r.sample_code not in online]
    if missing:raise RuntimeError(f'批次 {batch_code} 恢复校验失败，缺少 {", ".join(missing[:3])}，已回滚该批')
    db.execute(delete(ArchivedInspection).where(ArchivedInspection.id.in_([r.id for r in rows])))
    a.archived_samples=int(db.scalar(select(func.count()).select_from(ArchivedInspection).where(ArchivedInspection.month==a.month)) or 0)
    _set_progress(a,batch_code,'restored',len(rows))
    db.commit()
    return len(rows)

def run_restore(db,archive_id):
    key=f'mill:archive:{archive_id}'
    if not _advisory_lock(db,key):return
    try:
        a=db.get(Archive,archive_id)
        # 只处理仍处于待恢复/恢复中的存档；陈旧队列项直接忽略
        if not a or a.operation!='restore' or a.status not in ('pending','restoring'):return
        a.status='restoring';a.error='';a.updated_at=now();db.commit()
        rounds=0
        while True:
            rounds+=1
            if rounds>20:break
            codes=[c for (c,) in db.execute(select(ArchivedInspection.batch_code).where(ArchivedInspection.month==a.month)
                                             .group_by(ArchivedInspection.batch_code).order_by(ArchivedInspection.batch_code)).all()]
            if not codes:break
            for code in codes:
                db.refresh(a)
                if a.status!='restoring':return
                _restore_one_batch(db,a,code)
        v=verify_month(db,a.month,persist=False)
        if not v['ok']:
            a.status='corrupt';a.error='；'.join(v['problems']);a.updated_at=now();db.commit();return
        a.archived_samples=0;a.status='restored';a.restored_at=now();a.updated_at=now();db.commit()
    except Exception as e:
        db.rollback()
        a=db.get(Archive,archive_id)
        if a:
            a.status='failed';a.error=str(e);a.updated_at=now();db.commit()
    finally:
        _advisory_unlock(db,key)

# ---------- 受理入口 ----------
def _enqueue(archive_id):
    queue.rpush(ARCHIVE_QUEUE,archive_id)

def start_archive(db,month,user):
    if month not in _months_in_play(db):raise HTTPException(404,'该到货月份没有批次记录')
    a=db.scalar(select(Archive).where(Archive.month==month))
    if a and a.status=='corrupt':raise HTTPException(409,f'归档 {month} 已损坏或缺失，已阻止继续归档；请先恢复或修复，避免掩盖缺失样本。')
    if a and a.status in ('migrating','restoring'):raise HTTPException(409,f'归档 {month} 正在进行中，请等待当前任务结束')
    online=db.scalar(select(func.count(func.distinct(Inspection.sample_code))).join(Batch,Batch.id==Inspection.batch_id)
                     .where(func.substr(Batch.received_date,1,7)==month)) or 0
    if not online:raise HTTPException(409,f'月份 {month} 没有待迁移的在线样本')
    if not a:
        a=Archive(month=month,created_by=user.email,batches=[]);db.add(a)
    elif a.status in ('ready','restored'):
        a.batches=[]  # 新一轮归档：重算批次进度，失败续跑时保留断点
    a.status='pending';a.operation='archive';a.error='';a.updated_at=now()
    if not a.batches:a.batches=[]
    db.commit()
    try:_enqueue(a.id)
    except Exception:
        a.status='failed';a.error='队列不可用，请恢复后重新提交';db.commit();raise HTTPException(503,a.error)
    return record_archive(db,a)

def start_restore(db,month,user):
    a=db.scalar(select(Archive).where(Archive.month==month))
    if not a:raise HTTPException(404,f'月份 {month} 尚未归档，无需恢复')
    if a.status=='corrupt':raise HTTPException(409,f'归档 {month} 已损坏或缺失，已阻止恢复；请人工核对缺失样本后再处理。')
    if a.status in ('migrating','restoring'):raise HTTPException(409,f'归档 {month} 正在进行中，请等待当前任务结束')
    if not a.archived_samples:raise HTTPException(409,f'月份 {month} 没有归档样本可恢复')
    a.status='restoring';a.operation='restore';a.error='';a.updated_at=now();db.commit()
    try:_enqueue(a.id)
    except Exception:
        a.status='ready';a.error='队列不可用，请恢复后重新提交';db.commit();raise HTTPException(503,a.error)
    return record_archive(db,a)

def record_archive(db,a):
    online=db.scalar(select(func.count(func.distinct(Inspection.sample_code))).join(Batch,Batch.id==Inspection.batch_id)
                     .where(func.substr(Batch.received_date,1,7)==a.month)) or 0
    archived=int(db.scalar(select(func.count()).select_from(ArchivedInspection).where(ArchivedInspection.month==a.month)) or 0)
    return {'id':a.id,'month':a.month,'status':a.status,'operation':a.operation,'expected_samples':a.archived_samples,
            'archived_samples':archived,'online_samples':online,'checksum':a.checksum,'error':a.error,
            'created_by':a.created_by,'created_at':a.created_at.isoformat() if a.created_at else '',
            'updated_at':a.updated_at.isoformat() if a.updated_at else '',
            'completed_at':a.completed_at.isoformat() if a.completed_at else '',
            'restored_at':a.restored_at.isoformat() if a.restored_at else '','progress':_archive_progress(a)}
