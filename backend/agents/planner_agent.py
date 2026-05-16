import logging
from datetime import datetime
from agent.planner import plan_workflow

logger = logging.getLogger(__name__)

class PlannerAgent:
    async def run(self, state: dict) -> dict:
        logger.info({"event": "agent_start", "component": "PlannerAgent", "trace_id": state.get("workflow_id")})
        state = await plan_workflow(state)
        logger.info({"event": "agent_complete", "component": "PlannerAgent", "trace_id": state.get("workflow_id")})
        return state
