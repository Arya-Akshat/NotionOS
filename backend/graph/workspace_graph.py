import logging

logger = logging.getLogger(__name__)

def get_workspace_graph() -> dict:
    try:
        return {
            "nodes": [
                {"id": "db_tasks", "label": "Task Database", "type": "database"},
                {"id": "doc_roadmap", "label": "Project Notes", "type": "note"},
                {"id": "task_1", "label": "Launch AI SaaS MVP", "type": "task"}
            ],
            "edges": [
                {"source": "task_1", "target": "db_tasks", "type": "parent-child"},
                {"source": "task_1", "target": "doc_roadmap", "type": "relation"}
            ]
        }
    except Exception as e:
        logger.warning(f"Failed to build workspace graph: {e}")
        return {"nodes": [], "edges": []}
