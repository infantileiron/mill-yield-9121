from sqlalchemy import create_engine,text
from sqlalchemy.orm import sessionmaker, DeclarativeBase
from src.config.settings import DATABASE_URL
engine=create_engine(DATABASE_URL, pool_pre_ping=True)
Session=sessionmaker(engine, expire_on_commit=False)
class Base(DeclarativeBase): pass
def get_db():
    with Session() as s: yield s
def ensure_schema():
    """create_all 不会给已有表补列；为旧库补齐归档新增列。"""
    Base.metadata.create_all(engine)
    if engine.dialect.name!='postgresql':return
    with engine.begin() as conn:
        conn.execute(text("ALTER TABLE reviews ADD COLUMN IF NOT EXISTS month VARCHAR(7) DEFAULT '全部'"))
