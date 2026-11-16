from enum import Enum
class Role(str,Enum):
    admin="admin"
    analyst="analyst"
    viewer="viewer"
class ReviewStatus(str,Enum):
    queued="queued"
    running="running"
    completed="completed"
    approved="approved"
    failed="failed"
LINES=["一线","二线","三线"]
