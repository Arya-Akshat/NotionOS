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
    Analyzes the task and generates the structured execution plan.
    With 30s timeout and error hardening.
    """
    
    from agent.intent_parser import is_project_scaffolding_task, generate_scaffolding_plan
    print(f"[Planner] Input Task Text: {state['task_text'][:500]}...")
    try:
        from agent.intent_parser import is_project_scaffolding_task, generate_scaffolding_plan
        is_scaffolding = is_project_scaffolding_task(state["task_text"])
        print(f"[Planner] is_scaffolding: {is_scaffolding}")
        scaffolding_plan = None
        if is_scaffolding:
            scaffolding_plan = generate_scaffolding_plan(
                state["task_text"],
                state.get("workspace_style", {}),
                state.get("workspace_context", {}).get("related_pages", [])
            )
            state["is_scaffolding"] = True
            state["workspace_preview"] = scaffolding_plan["workspace_preview"]

        # Wrap planner in a 30-second timeout to fetch other tool actions
        parsed_result = await asyncio.wait_for(
            parse_intent("Task", state["task_text"]),
            timeout=30.0
        )
        
        if parsed_result["success"]:
            state["goal"] = parsed_result["data"]["goal"]
            llm_plan = parsed_result["data"]["actions"]
            
            if is_scaffolding:
                state["execution_plan"] = [{"type": "scaffolding", "data": scaffolding_plan}] + llm_plan
            else:
                state["execution_plan"] = llm_plan
                
            state["status"] = "WAITING_FOR_APPROVAL"
        else:
            if is_scaffolding:
                state["execution_plan"] = [{"type": "scaffolding", "data": scaffolding_plan}]
                state["goal"] = scaffolding_plan["goal"]
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
