from sqlalchemy import select,func
from sqlalchemy.exc import IntegrityError
from fastapi import HTTPException
from redis import Redis
from src.config.settings import REDIS_URL
from src.models.entities import Batch,Inspection,Review,ArchivedInspection
from src.services import archive as archive_service
from src.utils.serialize import record
queue=Redis.from_url(REDIS_URL,decode_responses=True)
def batches(db):
    counts=archive_service.batch_counts(db)
    rows=db.execute(select(Batch).order_by(Batch.id.desc())).scalars().all()
    return [{**record(b),'samples':counts.get(b.id,0)} for b in rows]
def create(db,model,data):
    obj=model(**data);db.add(obj)
    try:db.commit()
    except IntegrityError:
        db.rollback();raise HTTPException(409,'编号已存在，请使用独立编号')
    return record(obj)
def inspections(db,batch_id=None,month=None):
    rows=archive_service.samples_view(db,month)
    if batch_id:rows=[x for x in rows if x['batch_id']==batch_id]
    for x in rows:
        for k in ('archived','month','batch_seq'):
            x.pop(k,None)
    return rows
def add_inspection(db,data):
    if not db.get(Batch,data['batch_id']):raise HTTPException(404,'原粮批次不存在')
    if db.scalar(select(ArchivedInspection.id).where(ArchivedInspection.sample_code==data['sample_code'])):
        raise HTTPException(409,f"样本编号 {data['sample_code']} 已归档，不能重复录入；如需更正请先恢复该批次所属月份")
    obj=Inspection(**data);db.add(obj)
    try:db.flush()
    except IntegrityError:
        db.rollback();raise HTTPException(409,'编号已存在，请使用独立编号')
    db.commit()
    return record(obj)
def submit(db,data,user):
    month=data.pop('month','全部')
    # 归档损坏时阻止分析，避免静默少算；快照在单条 UNION 查询中取完整视图
    archive_service.ensure_readable(db,month)
    rows=inspections(db,month=None if month=='全部' else month)
    if data['line']!='全部':rows=[x for x in rows if x['line']==data['line']]
    if len(rows)<5:raise HTTPException(422,'该范围至少需要 5 条检验记录，请先录入')
    obj=Review(**data,month=month,created_by=user.email,snapshot=rows);db.add(obj);db.commit()
    try:queue.rpush('mill:jobs',obj.id)
    except Exception:
        obj.status='failed';obj.note='队列不可用，请恢复后重新提交';db.commit();raise HTTPException(503,obj.note)
    return record(obj)
def review(db,id):
    obj=db.get(Review,id)
    if not obj:raise HTTPException(404,'复核单不存在')
    return obj
def snapshot_archive_health(db,obj):
    """报告查证时核对快照涉及的归档月份；损坏/缺失则明确提示，不静默沿用旧值。"""
    months=sorted({x.get('month') or archive_service.month_of(x.get('received_date')) for x in (obj.snapshot or [])})
    problems=[]
    for m in months:
        if not m:continue
        v=archive_service.verify_month(db,m)
        if not v['ok']:problems.append({'month':m,'problems':v['problems']})
    return {'ok':not problems,'months':months,'problems':problems}
def approve(db,id,note,user):
    obj=review(db,id)
    if obj.status!='completed':raise HTTPException(409,'只有已计算且未签核的复核单可以签核')
    obj.status='approved';obj.note=note;obj.approved_by=user.email;db.commit()
    return record(obj)
