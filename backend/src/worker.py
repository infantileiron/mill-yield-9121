import time,os,traceback
from pathlib import Path
from sqlalchemy import select
from src.config.database import Session,Base,engine
from src.models.entities import Review
from src.services.business import queue
from src.services.statistics import diagnose
Base.metadata.create_all(engine)
# Recover committed jobs if a process stopped between database commit and queue push.
with Session() as db:
    for obj in db.scalars(select(Review).where(Review.status.in_(['queued','running']))):queue.rpush('mill:jobs',obj.id)
while True:
    Path('/tmp/worker-heartbeat').touch()
    item=queue.blpop('mill:jobs',timeout=2)
    if not item:continue
    with Session() as db:
        obj=db.get(Review,int(item[1]))
        if not obj or obj.status not in ('queued','running'):continue
        obj.status='running';db.commit()
        try:
            obj.result=diagnose(obj.snapshot);obj.status='completed'
            Path('/artifacts').mkdir(exist_ok=True)
            Path(f'/artifacts/review-{obj.id}.json').write_text(__import__('json').dumps(obj.result,ensure_ascii=False))
        except Exception as e:obj.status='failed';obj.note=str(e);traceback.print_exc()
        db.commit()
