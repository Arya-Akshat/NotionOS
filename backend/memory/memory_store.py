from sqlalchemy.orm import Session
from database import TaskRun

def get_recent_task_memories(db: Session, limit: int = 5):
    try:
        runs = db.query(TaskRun).filter(TaskRun.status == 'COMPLETED').order_by(TaskRun.id.desc()).limit(limit).all()
        return [{"task_title": r.title, "status": "COMPLETED"} for r in runs]
    except Exception as e:
        return []
