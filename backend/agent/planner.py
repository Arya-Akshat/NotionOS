from typing import TypedDict, Annotated, Sequence
import operator
from langchain_core.messages import BaseMessage
from backend.agent.intent_parser import parse_intent

# Clear Agent States
class AgentState(TypedDict):
    task_id: str
    original_text: str
    status: str # "PENDING", "PLANNING", "EXECUTING", "COMPLETED", "FAILED"
    goal: str
    execution_plan: list         # [{tool, args}] dicts
    current_step: int
    tool_outputs: dict
    errors: list[str]
    workflow_id: int             # DB primary key for AgentRun
    messages: Annotated[Sequence[BaseMessage], operator.add]

def plan_workflow(state: AgentState):
    """
    Analyzes the task and updates state to PLANNING, generating the structured execution plan.
    """
    state["status"] = "PLANNING"
    parsed_result = parse_intent(state["original_text"])
    
    if parsed_result["success"]:
        state["goal"] = parsed_result["data"]["goal"]
        state["execution_plan"] = parsed_result["data"]["actions"]
        state["status"] = "EXECUTING"
    else:
        state["errors"] = state.get("errors", []) + [parsed_result["error"]]
        state["status"] = "FAILED"
        
    return state
