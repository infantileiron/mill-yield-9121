from pydantic import BaseModel,Field,field_validator
from typing import Literal
class Login(BaseModel):
    email:str
    password:str
class BatchInput(BaseModel):
    code:str=Field(min_length=3,max_length=50,pattern=r"^[A-Za-z0-9_-]+$")
    line:Literal["一线","二线","三线"]
    supplier:str=Field(min_length=1,max_length=80)
    tonnes:float=Field(gt=0,le=10000,allow_inf_nan=False)
    received_date:str
    @field_validator('received_date')
    @classmethod
    def valid_date(cls,v):
        from datetime import date
        date.fromisoformat(v)
        return v
class InspectionInput(BaseModel):
    sample_code:str=Field(min_length=3,max_length=70,pattern=r"^[A-Za-z0-9_-]+$")
    batch_id:int=Field(gt=0)
    flour_yield:float=Field(gt=0,le=100,allow_inf_nan=False)
    moisture:float=Field(ge=0,le=30,allow_inf_nan=False)
    inspector:str=Field(min_length=1,max_length=50)
class ReviewInput(BaseModel):
    title:str=Field(min_length=2,max_length=120)
    line:Literal["全部","一线","二线","三线"]="全部"
    month:str=Field(default="全部",pattern=r"^(全部|\d{4}-(0[1-9]|1[0-2]))$")
class ArchiveInput(BaseModel):
    month:str=Field(pattern=r"^\d{4}-(0[1-9]|1[0-2])$")
class ApprovalInput(BaseModel):
    note:str=Field(min_length=5,max_length=1500)
