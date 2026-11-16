import random
from sqlalchemy import select,func
from src.config.database import Session,Base,engine
from src.models.entities import User,Batch,Inspection,Review
from src.utils.security import password_hash
from src.services.statistics import diagnose
def seed():
    Base.metadata.create_all(engine);rng=random.Random(3101)
    with Session() as db:
        for role in ['admin','analyst','viewer']:
            email=f'{role}@demo.local'
            if not db.scalar(select(User).where(User.email==email)):db.add(User(email=email,password_hash=password_hash('Demo123!'),role=role))
        db.flush()
        for i in range(40):
            code='QH-1115-A' if i==0 else f'QH-{1101+i:04}-B'
            batch=db.scalar(select(Batch).where(Batch.code==code))
            if not batch:
                batch=Batch(code=code,line=['一线','二线','三线'][i%3],supplier=['丰垦粮业','北原合作社','河谷粮仓'][i%3],tonnes=round(25+i*.7,1),received_date=f'2026-11-{1+i%15:02}')
                db.add(batch);db.flush()
            for j in range(15):
                sc=f'{code}-S{j+1:02}';val=round(max(65,min(82,rng.gauss(73+i%3*1.4,1.6))),2)
                if i in (0,9,25) and j==14:val=65.0 if i==0 else 82.0
                moisture=round(rng.uniform(11.5,14.2),2)
                if not db.scalar(select(Inspection).where(Inspection.sample_code==sc)):
                    db.add(Inspection(sample_code=sc,batch_id=batch.id,flour_yield=val,moisture=moisture,inspector=['林洁','周麦','陈禾'][i%3]))
        db.flush()
        if not db.scalar(select(Review).where(Review.title=='11月15日全线出粉率初审')):
            from src.services.business import inspections
            rows=inspections(db)
            db.add(Review(title='11月15日全线出粉率初审',line='全部',status='completed',snapshot=rows,result=diagnose(rows),created_by='analyst@demo.local',note='待质量负责人核对异常点及签核'))
        db.commit()
        print({m.__tablename__:db.scalar(select(func.count()).select_from(m)) for m in [Batch,Inspection,Review]})
if __name__=='__main__':seed()
