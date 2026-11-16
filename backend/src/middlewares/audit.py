from starlette.middleware.base import BaseHTTPMiddleware
from src.config.database import Session
from src.models.entities import Audit
class AuditMiddleware(BaseHTTPMiddleware):
    async def dispatch(self,request,call_next):
        response=await call_next(request)
        if request.method in ('POST','PUT','DELETE','PATCH'):
            try:
                with Session() as db:
                    db.add(Audit(actor=getattr(request.state,'actor','anonymous'),action=request.method+' '+request.url.path,status=response.status_code));db.commit()
            except Exception:pass
        return response
