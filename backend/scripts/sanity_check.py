"""
Sanity check script for NotionOS.
Verifies critical logic without requiring full external API connectivity.
"""

import sys
import os
from unittest.mock import MagicMock, patch

# Ensure backend is in path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.agent.planner import plan_workflow
from backend.agent.executor import execute_tools, VALID_NOTION_STATUSES
from backend.agent.intent_parser import parse_intent

def test_planner_failure():
    print("Testing planner failure path...")
    state = {
        "original_text": "invalid task",
        "status": "PENDING",
        "errors": []
    }
    
    with patch("backend.agent.planner.parse_intent") as mock_parse:
        mock_parse.return_value = {"success": False, "error": "Simulated planner failure"}
        state = plan_workflow(state)
        
        assert state["status"] == "FAILED"
        assert "Simulated planner failure" in state["errors"]
    print("✅ Planner failure path remains FAILED")

def test_executor_args_passing():
    print("Testing executor argument passing...")
    state = {
        "status": "EXECUTING",
        "execution_plan": [{"tool": "test_tool", "args": {"foo": "bar"}}],
        "current_step": 0,
        "tool_outputs": {}
    }
    
    mock_tool = MagicMock(return_value={"success": True, "data": "ok"})
    with patch("backend.agent.executor.TOOL_MAP", {"test_tool": mock_tool}):
        state = execute_tools(state)
        
        mock_tool.assert_called_once_with(foo="bar")
        assert state["tool_outputs"]["test_tool"]["success"] is True
    print("✅ Executor passes args to tools correctly")

def test_notion_status_vocab():
    print("Testing Notion status vocabulary...")
    allowed = {"Pending", "In Progress", "COMPLETED", "FAILED"}
    assert VALID_NOTION_STATUSES == allowed
    print("✅ Notion status values are from allowed set")

def test_ws_dispatch_trigger():
    print("Testing WebSocket dispatch trigger...")
    from backend.workflows.task_agent import log_tool_call
    
    # Mock database session and main dispatcher
    mock_db = MagicMock()
    with patch("backend.workflows.task_agent.SessionLocal", return_value=mock_db):
        with patch("backend.main.dispatch_broadcast") as mock_dispatch:
            log_tool_call(
                agent_run_id=1,
                tool_name="test_tool",
                tool_input={"a": 1},
                result={"success": True, "data": {"res": "ok"}, "duration_ms": 100}
            )
            
            # Verify dispatch was called with expected event type
            assert mock_dispatch.called
            args, _ = mock_dispatch.call_args
            assert args[0]["type"] == "tool_call_logged"
            assert args[0]["run_id"] == 1
        
    print("✅ log_tool_call triggers dispatch_broadcast")

if __name__ == "__main__":
    try:
        test_planner_failure()
        test_executor_args_passing()
        test_notion_status_vocab()
        test_ws_dispatch_trigger()
        print("\n✨ All sanity checks passed!")
    except Exception as e:
        print(f"\n❌ Sanity check failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
