from datetime import datetime
def record(obj):
    return {c.name:(getattr(obj,c.name).isoformat() if isinstance(getattr(obj,c.name),datetime) else getattr(obj,c.name)) for c in obj.__table__.columns}
