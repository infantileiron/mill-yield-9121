from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse
import time
from redis import Redis
from src.config.settings import REDIS_URL
class RateLimitMiddleware(BaseHTTPMiddleware):
    async def dispatch(self,request,call_next):
        if request.url.path!='/health':
            try:
                redis=Redis.from_url(REDIS_URL);key=f'mill:limit:{request.client.host}:{int(time.time()//60)}'
                n=redis.incr(key)
                if n==1:redis.expire(key,65)
                if n>240:return JSONResponse({'detail':'请求频率过高，请一分钟后重试'},429)
            except Exception:return JSONResponse({'detail':'限流服务暂不可用，请重试'},503)
        return await call_next(request)
