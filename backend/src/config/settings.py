import os
DATABASE_URL=os.getenv("DATABASE_URL", "postgresql+psycopg://mill:mill@db/mill")
REDIS_URL=os.getenv("REDIS_URL", "redis://redis:6379/0")
JWT_SECRET=os.getenv("JWT_SECRET", "local-mill-change-this-secret-at-least-32")
