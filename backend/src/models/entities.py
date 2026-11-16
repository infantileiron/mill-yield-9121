from sqlalchemy import String, Float, Integer, ForeignKey, JSON, Text, DateTime
from sqlalchemy.orm import Mapped, mapped_column
from datetime import datetime, timezone
from src.config.database import Base
class User(Base):
    __tablename__="users"
    id:Mapped[int]=mapped_column(primary_key=True)
    email:Mapped[str]=mapped_column(String(100),unique=True)
    password_hash:Mapped[str]=mapped_column(String(300))
    role:Mapped[str]=mapped_column(String(20))
class Batch(Base):
    __tablename__="batches"
    id:Mapped[int]=mapped_column(primary_key=True)
    code:Mapped[str]=mapped_column(String(50),unique=True)
    line:Mapped[str]=mapped_column(String(20))
    supplier:Mapped[str]=mapped_column(String(80))
    tonnes:Mapped[float]=mapped_column(Float)
    received_date:Mapped[str]=mapped_column(String(10))
class Inspection(Base):
    __tablename__="inspections"
    id:Mapped[int]=mapped_column(primary_key=True)
    sample_code:Mapped[str]=mapped_column(String(70),unique=True)
    batch_id:Mapped[int]=mapped_column(ForeignKey("batches.id"))
    flour_yield:Mapped[float]=mapped_column(Float)
    moisture:Mapped[float]=mapped_column(Float)
    inspector:Mapped[str]=mapped_column(String(50))
class Review(Base):
    __tablename__="reviews"
    id:Mapped[int]=mapped_column(primary_key=True)
    title:Mapped[str]=mapped_column(String(120))
    line:Mapped[str]=mapped_column(String(20))
    month:Mapped[str]=mapped_column(String(7),default="全部")
    status:Mapped[str]=mapped_column(String(20),default="queued")
    result:Mapped[dict]=mapped_column(JSON,default=dict)
    snapshot:Mapped[list]=mapped_column(JSON,default=list)
    note:Mapped[str]=mapped_column(Text,default="")
    created_by:Mapped[str]=mapped_column(String(100))
    approved_by:Mapped[str]=mapped_column(String(100),default="")
    created_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),default=lambda:datetime.now(timezone.utc))
class Archive(Base):
    __tablename__="archives"
    id:Mapped[int]=mapped_column(primary_key=True)
    month:Mapped[str]=mapped_column(String(7),unique=True,index=True)
    status:Mapped[str]=mapped_column(String(20),default="pending")
    operation:Mapped[str]=mapped_column(String(20),default="")
    expected_samples:Mapped[int]=mapped_column(Integer,default=0)
    archived_samples:Mapped[int]=mapped_column(Integer,default=0)
    checksum:Mapped[str]=mapped_column(String(64),default="")
    batches:Mapped[list]=mapped_column(JSON,default=list)
    error:Mapped[str]=mapped_column(Text,default="")
    created_by:Mapped[str]=mapped_column(String(100),default="")
    created_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),default=lambda:datetime.now(timezone.utc))
    updated_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),default=lambda:datetime.now(timezone.utc))
    completed_at:Mapped[datetime|None]=mapped_column(DateTime(timezone=True),nullable=True)
    restored_at:Mapped[datetime|None]=mapped_column(DateTime(timezone=True),nullable=True)


class ArchivedInspection(Base):
    __tablename__="archived_inspections"
    id:Mapped[int]=mapped_column(primary_key=True)
    archive_id:Mapped[int]=mapped_column(ForeignKey("archives.id"),index=True)
    month:Mapped[str]=mapped_column(String(7),index=True)
    origin_id:Mapped[int]=mapped_column(Integer)
    sample_code:Mapped[str]=mapped_column(String(70),unique=True)
    batch_id:Mapped[int]=mapped_column(Integer,index=True)
    batch_code:Mapped[str]=mapped_column(String(50))
    line:Mapped[str]=mapped_column(String(20))
    received_date:Mapped[str]=mapped_column(String(10))
    flour_yield:Mapped[float]=mapped_column(Float)
    moisture:Mapped[float]=mapped_column(Float)
    inspector:Mapped[str]=mapped_column(String(50))
    row_checksum:Mapped[str]=mapped_column(String(64))


class Audit(Base):
    __tablename__="audits"
    id:Mapped[int]=mapped_column(primary_key=True)
    actor:Mapped[str]=mapped_column(String(100))
    action:Mapped[str]=mapped_column(String(200))
    status:Mapped[int]=mapped_column(Integer)
    created_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),default=lambda:datetime.now(timezone.utc))
