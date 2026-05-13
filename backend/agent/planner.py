import asyncio
from typing import TypedDict, Annotated, Sequence
import operator
from langchain_core.messages import BaseMessage
from agent.intent_parser import parse_intent
from database import SessionLocal
from models.logs import AgentRun

# Clear Agent States
class AgentState(TypedDict):
    task_id: str
    task_text: str
    status: str # "PENDING", "PLANNING", "EXECUTING", "COMPLETED", "FAILED"
    goal: str
    execution_plan: list         # [{tool, args}] dicts
    current_step: int
    tool_outputs: dict
    errors: list[str]
    workflow_id: int             # DB primary key for AgentRun
    messages: Annotated[Sequence[BaseMessage], operator.add]

async def plan_workflow(state: AgentState):
    """
    Analyzes the task and updates state to PLANNING, generating the structured execution plan.
    With 30s timeout and error hardening.
    """
    state["status"] = "PLANNING"
    
    try:
        # Wrap planner in a 30-second timeout
        parsed_result = await asyncio.wait_for(
            parse_intent("Task", state["task_text"]),
            timeout=30.0
        )
        
        if parsed_result["success"]:
            state["goal"] = parsed_result["data"]["goal"]
            state["execution_plan"] = parsed_result["data"]["actions"]
            state["status"] = "WAITING_FOR_APPROVAL"
        else:
            state["errors"] = state.get("errors", []) + [parsed_result["error"]]
            state["status"] = "FAILED"
            
    except asyncio.TimeoutError:
        state["errors"] = state.get("errors", []) + ["Planner timed out after 30 seconds"]
        state["status"] = "FAILED"
    except Exception as e:
        state["errors"] = state.get("errors", []) + [f"Planner error: {str(e)}"]
        state["status"] = "FAILED"
        
    # Sync status to DB immediately to avoid duplicate pickup
    wf_id = state.get("workflow_id")
    if wf_id:
        db = SessionLocal()
        try:
            run = db.query(AgentRun).filter(AgentRun.id == wf_id).first()
            if run:
                run.status = state["status"]
                run.goal = state.get("goal", "")
                run.execution_plan = state.get("execution_plan", [])
                db.commit()
        finally:
            db.close()
            
    return state
