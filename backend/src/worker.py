import time,os,traceback
from pathlib import Path
from sqlalchemy import select
from src.config.database import Session,Base,engine,ensure_schema
from src.models.entities import Review,Archive
from src.services.business import queue
from src.services.statistics import diagnose
from src.services.archive import ARCHIVE_QUEUE,run_archive,run_restore,BUSY_STATES
import json
ensure_schema()
# Recover committed jobs if a process stopped between database commit and queue push.
with Session() as db:
    for obj in db.scalars(select(Review).where(Review.status.in_(['queued','running']))):queue.rpush('mill:jobs',obj.id)
    # 归档/恢复中断后续跑：尚未完成的月份重新排队（服务层按批幂等，不会重复写入）
    for a in db.scalars(select(Archive).where(Archive.status.in_(list(BUSY_STATES)))):
        queue.rpush(ARCHIVE_QUEUE,a.id)
while True:
    Path('/tmp/worker-heartbeat').touch()
    item=queue.blpop(['mill:jobs',ARCHIVE_QUEUE],timeout=2)
    if not item:continue
    job_queue,job_id=item[0],int(item[1])
    if job_queue==ARCHIVE_QUEUE:
        with Session() as db:
            a=db.get(Archive,job_id)
            if not a or a.status not in BUSY_STATES:continue
            op=a.operation
        try:
            with Session() as db:
                if op=='restore':run_restore(db,job_id)
                else:run_archive(db,job_id)
        except Exception:traceback.print_exc()
        continue
    with Session() as db:
        obj=db.get(Review,job_id)
        if not obj or obj.status not in ('queued','running'):continue
        obj.status='running';db.commit()
        try:
            obj.result=diagnose(obj.snapshot);obj.status='completed'
            Path('/artifacts').mkdir(exist_ok=True)
            Path(f'/artifacts/review-{obj.id}.json').write_text(json.dumps(obj.result,ensure_ascii=False))
        except Exception as e:obj.status='failed';obj.note=str(e);traceback.print_exc()
        db.commit()
