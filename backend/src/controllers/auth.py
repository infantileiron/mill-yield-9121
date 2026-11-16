from fastapi import Depends,HTTPException,Request
from fastapi.security import HTTPBearer,HTTPAuthorizationCredentials
from sqlalchemy import select
import jwt
from src.config.database import get_db
from src.config.settings import JWT_SECRET
from src.models.entities import User
from src.utils.security import verify,issue
bearer=HTTPBearer(auto_error=False)
def current(request:Request,cred:HTTPAuthorizationCredentials=Depends(bearer),db=Depends(get_db)):
    try:
        if not cred:raise ValueError()
        uid=int(jwt.decode(cred.credentials,JWT_SECRET,algorithms=['HS256'])['sub']);u=db.get(User,uid)
        if not u:raise ValueError()
    except Exception:raise HTTPException(401,'登录已过期，请重新登录')
    request.state.actor=u.email
    return u
def writable(u=Depends(current)):
    if u.role not in ('admin','analyst'):raise HTTPException(403,'观察员只可读取，无法写入或提交计算')
    return u
def admin(u=Depends(current)):
    if u.role!='admin':raise HTTPException(403,'复核签核仅限质量负责人')
    return u
def login(db,data):
    u=db.scalar(select(User).where(User.email==data.email))
    if not u or not verify(data.password,u.password_hash):raise HTTPException(401,'邮箱或密码错误')
    return {'access_token':issue(u),'user':{'email':u.email,'role':u.role}}
