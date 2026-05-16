import asyncio
import logging
from datetime import datetime
from notion_mcp.client import mcp_client
from tools.notion_tool import append_execution_update, update_notion_task_status
from database import SessionLocal
from models.logs import AgentRun

logger = logging.getLogger(__name__)

class ScaffoldingError(Exception):
    """Critical error during workspace scaffolding that requires aborting."""
    pass

ACTIVE_SCAFFOLDING_WORKFLOWS = set()

class ProjectScaffolder:
    async def build_workspace(
        self,
        project_name: str,
        task_page_id: str,
        workspace_style: dict,
        related_pages: list,
        prior_runs: list,
        workflow_id: str = None
    ) -> dict:
        """
        Builds the full project workspace in strict atomic order.
        """
        w_id = str(workflow_id) if workflow_id else project_name
        if w_id in ACTIVE_SCAFFOLDING_WORKFLOWS:
            print(f"[ProjectScaffolder] Duplicate scaffolding detected for {w_id}, skipping.")
            raise ScaffoldingError(f"Duplicate scaffolding detected for {w_id}")
        
        ACTIVE_SCAFFOLDING_WORKFLOWS.add(w_id)
        
        result = {
            "success": False,
            "parent_page_id": None,
            "brief_page_id": None,
            "roadmap_page_id": None,
            "database_id": None,
            "pages_created": [],
            "errors": [],
            "execution_log": []
        }
        
        try:
            # STEP 1: Create Parent Page
            await append_execution_update(task_page_id, "Parent Page", "running")
            parent_id = await self._create_parent_page(project_name, task_page_id, workspace_style)
            result["parent_page_id"] = parent_id
            result["pages_created"].append("Parent Page")
            result["execution_log"].append(f"✅ Created parent page '{project_name}'")
            await append_execution_update(task_page_id, "Parent Page", "complete")
            await asyncio.sleep(0.5)

            # STEP 2: Create Project Brief
            await append_execution_update(task_page_id, "Project Brief", "running")
            try:
                brief_id = await self._create_project_brief(parent_id, project_name, workspace_style, related_pages)
                result["brief_page_id"] = brief_id
                result["pages_created"].append("Project Brief")
                result["execution_log"].append("✅ Created 'Project Brief'")
                await append_execution_update(task_page_id, "Project Brief", "complete")
            except Exception as e:
                result["errors"].append(f"Brief creation failed: {e}")
                result["execution_log"].append(f"❌ Failed to create 'Project Brief': {e}")
                await append_execution_update(task_page_id, "Project Brief", "failed", str(e))
            await asyncio.sleep(0.5)

            # STEP 3: Create Roadmap
            await append_execution_update(task_page_id, "Roadmap", "running")
            try:
                roadmap_id = await self._create_roadmap(parent_id, project_name, result.get("brief_page_id"), workspace_style, related_pages)
                result["roadmap_page_id"] = roadmap_id
                result["pages_created"].append("Roadmap")
                result["execution_log"].append("✅ Created 'Roadmap'")
                await append_execution_update(task_page_id, "Roadmap", "complete")
            except Exception as e:
                result["errors"].append(f"Roadmap creation failed: {e}")
                result["execution_log"].append(f"❌ Failed to create 'Roadmap': {e}")
                await append_execution_update(task_page_id, "Roadmap", "failed", str(e))
            await asyncio.sleep(0.5)

            # STEP 4: Create Task Database
            await append_execution_update(task_page_id, "Task Tracker", "running")
            try:
                db_id = await self._create_task_database(parent_id, project_name, workspace_style, result.get("brief_page_id"), result.get("roadmap_page_id"))
                result["database_id"] = db_id
                result["pages_created"].append("Task Tracker")
                result["execution_log"].append("✅ Created 'Task Tracker' database")
                await append_execution_update(task_page_id, "Task Tracker", "complete")
                
                # STEP 5: Create Views
                await append_execution_update(task_page_id, "Views", "running")
                view_res = await self._create_views(db_id)
                if view_res.get("fallback_message"):
                    await self._add_view_fallback_callout(parent_id, view_res["fallback_message"])
                    result["execution_log"].append("⚠️ Views created via guidance callout")
                    await append_execution_update(task_page_id, "Views", "complete", "Guidance added")
                else:
                    result["execution_log"].append("✅ Kanban + Calendar views created")
                    await append_execution_update(task_page_id, "Views", "complete")
            except Exception as e:
                result["errors"].append(f"Database/View creation failed: {e}")
                result["execution_log"].append(f"❌ Failed to create 'Task Tracker': {e}")
                await append_execution_update(task_page_id, "Task Tracker", "failed", str(e))
            await asyncio.sleep(0.5)

            # STEP 6: Append Execution Log
            await self._append_execution_log(parent_id, result["execution_log"])
            
            result["success"] = True
            result["execution_log"].append("✅ Scaffolding complete")
            await append_execution_update(task_page_id, "Scaffolding", "complete")
            
            # Update original task status to 'Done'
            await update_notion_task_status(task_page_id, "Done")
            
            # Explicit DB update for scaffolding completion
            db = SessionLocal()
            try:
                run = db.query(AgentRun).filter(AgentRun.id == workflow_id).first()
                if run:
                    run.status = "COMPLETED"
                    db.commit()
                    print(f"[ProjectScaffolder] Run {workflow_id} marked COMPLETED in DB.")
            finally:
                db.close()

        except ScaffoldingError as e:
            result["errors"].append(f"CRITICAL: {e}")
            result["execution_log"].append(f"❌ CRITICAL FAILURE: {e}")
            await append_execution_update(task_page_id, "Scaffolding", "failed", str(e))
        except Exception as e:
            result["errors"].append(f"Unexpected error: {e}")
            result["execution_log"].append(f"❌ Unexpected error during scaffolding: {e}")
            await append_execution_update(task_page_id, "Scaffolding", "failed", str(e))
        finally:
            ACTIVE_SCAFFOLDING_WORKFLOWS.discard(str(w_id))
            
        return result

    async def _create_parent_page(self, project_name: str, task_page_id: str, style: dict) -> str:
        print(f"[ProjectScaffolder] STEP 1: Creating parent page '{project_name}' as sub-page of {task_page_id}...")
        icon = "📁" if style.get("uses_emojis") else None
        
        from config import config
        # Create project page as a SUB-PAGE of the original task page
        args = {
            "parent": {"type": "page_id", "page_id": task_page_id}, 
            "properties": {
                "title": {"title": [{"text": {"content": project_name}}]}
            }
        }
        if icon:
            args["icon"] = {"type": "emoji", "emoji": icon}

        try:
            res = await mcp_client.invoke_tool("API-post-page", args)
            
            if not res or "id" not in res:
                print(f"[ProjectScaffolder] Create page failed or returned no ID: {res}")
                # Try workspace root as last resort
                print("[ProjectScaffolder] Retrying with workspace root...")
                args["parent"] = {"type": "workspace", "workspace": True}
                res = await mcp_client.invoke_tool("API-post-page", args)
                
            if not res or "id" not in res:
                raise ScaffoldingError(f"Could not create parent page via MCP. Response: {res}")
                
            parent_id = res["id"]
            print(f"[ProjectScaffolder] Parent page created: {parent_id}")
            
            # Add Dashboard Content
            today = datetime.now().strftime("%Y-%m-%d")
            dashboard_blocks = [
                {
                    "object": "block",
                    "type": "callout",
                    "callout": {
                        "rich_text": [{"type": "text", "text": {"content": f"Welcome to {project_name} workspace — scaffolded by NotionOS. This workspace contains your Project Brief, Roadmap, and Task Tracker. Start by reviewing the brief and updating it with your specific details."}}],
                        "icon": {"type": "emoji", "emoji": "🚀"}
                    }
                },
                {"object": "block", "type": "divider", "divider": {}},
                {"object": "block", "type": "heading_2", "heading_2": {"rich_text": [{"text": {"content": "Quick Links"}}]}},
                {"object": "block", "type": "bulleted_list_item", "bulleted_list_item": {"rich_text": [{"text": {"content": "📄 Project Brief — Goals, features, and context"}}]}},
                {"object": "block", "type": "bulleted_list_item", "bulleted_list_item": {"rich_text": [{"text": {"content": "🗺️ Roadmap — Phase-by-phase execution plan"}}]}},
                {"object": "block", "type": "bulleted_list_item", "bulleted_list_item": {"rich_text": [{"text": {"content": "✅ Task Tracker — All project tasks and status"}}]}},
                {"object": "block", "type": "divider", "divider": {}},
                {"object": "block", "type": "heading_2", "heading_2": {"rich_text": [{"text": {"content": "Project Status"}}]}},
                {"object": "block", "type": "paragraph", "paragraph": {"rich_text": [{"text": {"content": "🟡 Status: In Planning"}}]}},
                {"object": "block", "type": "paragraph", "paragraph": {"rich_text": [{"text": {"content": f"📅 Started: {today}"}}]}},
                {"object": "block", "type": "paragraph", "paragraph": {"rich_text": [{"text": {"content": "👤 Owner: To be assigned"}}]}}
            ]
            await mcp_client.append_blocks(parent_id, dashboard_blocks)
            
            return parent_id
        except Exception as e:
            print(f"[ProjectScaffolder] Error in _create_parent_page: {e}")
            raise ScaffoldingError(f"Failed to create parent page: {e}")

    async def _create_project_brief(self, parent_page_id: str, project_name: str, style: dict, related_pages: list) -> str:
        print(f"[ProjectScaffolder] STEP 2: Creating Project Brief for '{project_name}'...")
        from tools.workspace_reader import WorkspaceStyleAnalyzer
        title = WorkspaceStyleAnalyzer.apply_naming_style("Project Brief", style)
        
        domain = self._derive_domain(project_name)
        features = self._derive_features(project_name)
        
        children = [
            {
                "object": "block",
                "type": "callout",
                "callout": {
                    "rich_text": [{"type": "text", "text": {"content": "💡 This brief was generated by NotionOS based on your task. Update each section as your project evolves."}}],
                    "icon": {"type": "emoji", "emoji": "💡"}
                }
            },
            {"object": "block", "type": "heading_2", "heading_2": {"rich_text": [{"text": {"content": "Problem Statement"}}]}},
            {"object": "block", "type": "paragraph", "paragraph": {"rich_text": [{"text": {"content": f"{project_name} aims to solve the {domain} domain by providing users with a structured, reliable, and delightful experience that stands out in today's market."}}]}},
            {"object": "block", "type": "heading_2", "heading_2": {"rich_text": [{"text": {"content": "Goals & Success Metrics"}}]}},
            {"object": "block", "type": "bulleted_list_item", "bulleted_list_item": {"rich_text": [{"text": {"content": "Launch a working MVP within 4 weeks"}}]}},
            {"object": "block", "type": "bulleted_list_item", "bulleted_list_item": {"rich_text": [{"text": {"content": "Achieve first 100 users within 30 days of launch"}}]}},
            {"object": "block", "type": "bulleted_list_item", "bulleted_list_item": {"rich_text": [{"text": {"content": "Maintain user retention rate above 40%"}}]}},
            {"object": "block", "type": "bulleted_list_item", "bulleted_list_item": {"rich_text": [{"text": {"content": "Collect 50+ pieces of user feedback in beta"}}]}},
            {"object": "block", "type": "heading_2", "heading_2": {"rich_text": [{"text": {"content": "Target Users"}}]}},
            {"object": "block", "type": "paragraph", "paragraph": {"rich_text": [{"text": {"content": f"Early adopters and enthusiasts in the {domain} space who need a better solution than what is currently available. Focus on users who value efficiency and clean design."}}]}},
            {"object": "block", "type": "heading_2", "heading_2": {"rich_text": [{"text": {"content": "Key Features"}}]}}
        ]
        
        for feature in features:
            children.append({"object": "block", "type": "bulleted_list_item", "bulleted_list_item": {"rich_text": [{"text": {"content": feature}}]}})
            
        children.extend([
            {"object": "block", "type": "heading_2", "heading_2": {"rich_text": [{"text": {"content": "Tech Stack (placeholder)"}}]}},
            {"object": "block", "type": "paragraph", "paragraph": {"rich_text": [{"text": {"content": "To be defined by the team."}}]}},
            {"object": "block", "type": "heading_2", "heading_2": {"rich_text": [{"text": {"content": "Related Work"}}]}}
        ])
        
        if related_pages:
            for page in related_pages:
                children.append({
                    "object": "block",
                    "type": "paragraph",
                    "paragraph": {"rich_text": [{"type": "mention", "mention": {"type": "page", "page": {"id": page["id"]}}}]}
                })
        else:
            children.append({"object": "block", "type": "paragraph", "paragraph": {"rich_text": [{"text": {"content": "No related pages found in workspace yet."}, "annotations": {"italic": True}}]}})
            
        children.append({"object": "block", "type": "divider", "divider": {}})
        children.append({"object": "block", "type": "paragraph", "paragraph": {"rich_text": [{"text": {"content": "→ See Roadmap for timeline"}, "annotations": {"bold": True}}]}})
            
        args = {
            "parent": {"type": "page_id", "page_id": parent_page_id},
            "properties": {"title": {"title": [{"text": {"content": title}}]}},
            "children": children
        }
        res = await mcp_client.invoke_tool("API-post-page", args)
        if not res or not isinstance(res, dict) or "id" not in res:
             print(f"[ProjectScaffolder] Project Brief creation failed or returned malformed: {res}")
             raise ScaffoldingError(f"Failed to create Project Brief: {res}")
             
        print(f"[ProjectScaffolder] Project Brief created: {res.get('id')}")
        return res["id"]

    async def _create_roadmap(self, parent_page_id: str, project_name: str, brief_page_id: str, style: dict, related_pages: list) -> str:
        print(f"[ProjectScaffolder] STEP 3: Creating Roadmap for '{project_name}'...")
        from tools.workspace_reader import WorkspaceStyleAnalyzer
        title = WorkspaceStyleAnalyzer.apply_naming_style("Roadmap", style)
        
        children = [
            {
                "object": "block",
                "type": "callout",
                "callout": {
                    "rich_text": [{"type": "text", "text": {"content": "🗺️ This roadmap was scaffolded by NotionOS. Adjust timelines and milestones to match your actual plans."}}],
                    "icon": {"type": "emoji", "emoji": "🗺️"}
                }
            },
            {"object": "block", "type": "heading_2", "heading_2": {"rich_text": [{"text": {"content": "Phase 1: MVP"}}]}},
            {"object": "block", "type": "paragraph", "paragraph": {"rich_text": [{"text": {"content": "Goal: Build and ship the core feature set.\nTimeline: Weeks 1–4"}}]}},
            {"object": "block", "type": "bulleted_list_item", "bulleted_list_item": {"rich_text": [{"text": {"content": "Set up project infrastructure"}}]}},
            {"object": "block", "type": "bulleted_list_item", "bulleted_list_item": {"rich_text": [{"text": {"content": "Build core functionality"}}]}},
            {"object": "block", "type": "bulleted_list_item", "bulleted_list_item": {"rich_text": [{"text": {"content": "Internal testing and bug fixes"}}]}},
            {"object": "block", "type": "bulleted_list_item", "bulleted_list_item": {"rich_text": [{"text": {"content": "Soft launch to 10 beta users"}}]}},
            
            {"object": "block", "type": "heading_2", "heading_2": {"rich_text": [{"text": {"content": "Phase 2: Beta"}}]}},
            {"object": "block", "type": "paragraph", "paragraph": {"rich_text": [{"text": {"content": "Goal: Gather feedback and iterate rapidly.\nTimeline: Weeks 5–8"}}]}},
            {"object": "block", "type": "bulleted_list_item", "bulleted_list_item": {"rich_text": [{"text": {"content": "Onboard 50 beta users"}}]}},
            {"object": "block", "type": "bulleted_list_item", "bulleted_list_item": {"rich_text": [{"text": {"content": "Run weekly feedback sessions"}}]}},
            {"object": "block", "type": "bulleted_list_item", "bulleted_list_item": {"rich_text": [{"text": {"content": "Fix top 10 reported issues"}}]}},
            {"object": "block", "type": "bulleted_list_item", "bulleted_list_item": {"rich_text": [{"text": {"content": "Performance optimization"}}]}},
            
            {"object": "block", "type": "heading_2", "heading_2": {"rich_text": [{"text": {"content": "Phase 3: Launch 🚀"}}]}},
            {"object": "block", "type": "paragraph", "paragraph": {"rich_text": [{"text": {"content": "Goal: Public launch and growth.\nTimeline: Weeks 9–12"}}]}},
            {"object": "block", "type": "bulleted_list_item", "bulleted_list_item": {"rich_text": [{"text": {"content": "Marketing campaign launch"}}]}},
            {"object": "block", "type": "bulleted_list_item", "bulleted_list_item": {"rich_text": [{"text": {"content": "Product Hunt submission"}}]}},
            {"object": "block", "type": "bulleted_list_item", "bulleted_list_item": {"rich_text": [{"text": {"content": "Reach 100 active users"}}]}},
            {"object": "block", "type": "bulleted_list_item", "bulleted_list_item": {"rich_text": [{"text": {"content": "Set up support workflow"}}]}},
            
            {"object": "block", "type": "divider", "divider": {}}
        ]
        
        if brief_page_id:
            children.append({
                "object": "block",
                "paragraph": {"rich_text": [
                    {"type": "text", "text": {"content": "← Project Brief | "}},
                    {"type": "mention", "mention": {"type": "page", "page": {"id": brief_page_id}}},
                    {"type": "text", "text": {"content": " | Tasks tracked in Task Tracker →"}}
                ]}
            })
            
        args = {
            "parent": {"type": "page_id", "page_id": parent_page_id},
            "properties": {"title": {"title": [{"text": {"content": title}}]}},
            "children": children
        }
        res = await mcp_client.invoke_tool("API-post-page", args)
        if not res or not isinstance(res, dict) or "id" not in res:
             print(f"[ProjectScaffolder] Roadmap creation failed or returned malformed: {res}")
             raise ScaffoldingError(f"Failed to create Roadmap: {res}")
             
        print(f"[ProjectScaffolder] Roadmap created: {res.get('id')}")
        return res["id"]

    async def _create_task_database(self, parent_page_id: str, project_name: str, style: dict, brief_page_id: str, roadmap_page_id: str) -> str:
        print(f"[ProjectScaffolder] STEP 4: Creating Task Tracker database for '{project_name}'...")
        from tools.workspace_reader import WorkspaceStyleAnalyzer
        from config import config
        import requests
        
        db_name = WorkspaceStyleAnalyzer.apply_naming_style("Task Tracker", style)
        
        url = "https://api.notion.com/v1/databases"
        headers = {
            "Authorization": f"Bearer {config.NOTION_API_KEY}",
            "Notion-Version": "2022-06-28",
            "Content-Type": "application/json"
        }
        
        payload = {
            "parent": {"type": "page_id", "page_id": parent_page_id},
            "title": [{"type": "text", "text": {"content": db_name}}],
            "properties": {
                "Name": {"title": {}},
                "Status": {
                    "status": {
                        "options": [
                            {"name": "Not started", "color": "red"},
                            {"name": "In progress", "color": "yellow"},
                            {"name": "Done", "color": "green"}
                        ]
                    }
                },
                "Priority": {
                    "select": {
                        "options": [
                            {"name": "High", "color": "red"},
                            {"name": "Medium", "color": "yellow"},
                            {"name": "Low", "color": "blue"}
                        ]
                    }
                },
                "Due Date": {"date": {}},
                "Assignee": {"people": {}}
            }
        }
        
        try:
            print(f"[ProjectScaffolder] Sending direct HTTP POST to create database '{db_name}'...")
            resp = requests.post(url, headers=headers, json=payload, timeout=15)
            if resp.status_code == 200:
                database_id = resp.json()["id"]
                print(f"[ProjectScaffolder] Task Tracker database created: {database_id}")
                
                # Add starter tasks
                await self._add_starter_tasks(database_id)
                return database_id
            else:
                print(f"[ProjectScaffolder] Database creation failed: {resp.status_code} - {resp.text}")
                raise ScaffoldingError(f"Database creation failed: {resp.text}")
        except Exception as e:
            print(f"[ProjectScaffolder] Database creation error: {e}")
            raise ScaffoldingError(f"Database creation failed: {e}")

    def _get_database_schema(self) -> dict:
        return {
            "Name": {"type": "title", "title": {}},
            "Status": {"type": "status", "status": {
                "options": [
                    {"name": "Not started", "color": "default"},
                    {"name": "In progress", "color": "blue"},
                    {"name": "Done", "color": "green"}
                ]
            }},
            "Priority": {"type": "select", "select": {
                "options": [
                    {"name": "High", "color": "red"},
                    {"name": "Medium", "color": "yellow"},
                    {"name": "Low", "color": "gray"}
                ]
            }},
            "Due Date": {"type": "date", "date": {}},
            "Assignee": {"type": "people", "people": {}},
            "Project": {"type": "rich_text", "rich_text": {}} # Fallback to rich_text instead of relation for stability
        }

    async def _create_views(self, database_id: str) -> dict:
        print(f"[ProjectScaffolder] STEP 5: Creating database views for {database_id}...")
        result = {"kanban_created": False, "calendar_created": False, "fallback_message": None}
        
        try:
            # Attempt Kanban
            print("[ProjectScaffolder] Attempting Kanban view...")
            res_k = await mcp_client.invoke_tool("create_view", {
                "database_id": database_id,
                "name": "Board",
                "type": "board",
                "group_by": "Status"
            })
            result["kanban_created"] = bool(res_k)
            
            # Attempt Calendar
            print("[ProjectScaffolder] Attempting Calendar view...")
            res_c = await mcp_client.invoke_tool("create_view", {
                "database_id": database_id,
                "name": "Calendar",
                "type": "calendar",
                "group_by": "Due Date"
            })
            result["calendar_created"] = bool(res_c)
        except Exception as e:
            print(f"[ProjectScaffolder] View creation error: {e}")
            result["fallback_message"] = "💡 Tip: Open Task Tracker → Add View → Board (group by Status) for kanban, or Calendar (group by Due Date) for timeline view."
            
        if not result["kanban_created"] or not result["calendar_created"]:
             result["fallback_message"] = "💡 Tip: Open Task Tracker → Add View → Board (group by Status) for kanban, or Calendar (group by Due Date) for timeline view."
             
        return result

    async def _append_execution_log(self, parent_page_id: str, log_entries: list) -> None:
        children = [
            {
                "object": "block",
                "type": "toggle",
                "toggle": {
                    "rich_text": [{"text": {"content": "🤖 Agent Execution Log"}}],
                    "children": [
                        {
                            "object": "block",
                            "type": "paragraph",
                            "paragraph": {"rich_text": [{"text": {"content": entry}}]}
                        } for entry in log_entries
                    ]
                }
            }
        ]
        await mcp_client.append_blocks(parent_page_id, children)

    async def _add_view_fallback_callout(self, parent_page_id: str, message: str) -> None:
        children = [
            {
                "object": "block",
                "type": "callout",
                "callout": {
                    "rich_text": [{"type": "text", "text": {"content": message}}],
                    "icon": {"type": "emoji", "emoji": "💡"}
                }
            }
        ]
        await mcp_client.append_blocks(parent_page_id, children)

    def _derive_domain(self, project_name: str) -> str:
        name = project_name.lower()
        if "fitness" in name or "workout" in name or "gym" in name:
            return "fitness and wellness"
        if "finance" in name or "budget" in name or "money" in name or "expense" in name:
            return "financial management"
        if "saas" in name or "product" in name or "app" in name or "software" in name:
            return "digital product"
        return "this"

    def _derive_features(self, project_name: str) -> list:
        name = project_name.lower()
        if "fitness" in name or "workout" in name or "gym" in name:
            return ["Workout tracking", "Progress analytics", "Goal setting", "Community challenges"]
        if "finance" in name or "budget" in name or "money" in name or "expense" in name:
            return ["Expense tracking", "Budget planning", "Savings goals", "Spending insights"]
        if "saas" in name or "product" in name:
            return ["User dashboard", "API access", "Team collaboration", "Analytics"]
        return ["Core functionality", "User management", "Analytics dashboard", "Mobile support"]

    async def _add_starter_tasks(self, database_id: str) -> None:
        """Adds 5 starter tasks to the new database via direct HTTP."""
        from config import config
        import requests
        
        url = "https://api.notion.com/v1/pages"
        headers = {
            "Authorization": f"Bearer {config.NOTION_API_KEY}",
            "Content-Type": "application/json",
            "Notion-Version": "2022-06-28"
        }
        
        starter_tasks = [
            {"name": "Define project requirements", "status": "In progress", "priority": "High"},
            {"name": "Set up development environment", "status": "Not started", "priority": "High"},
            {"name": "Design core user flow", "status": "Not started", "priority": "Medium"},
            {"name": "Build MVP feature #1", "status": "Not started", "priority": "Medium"},
            {"name": "Set up user feedback channel", "status": "Not started", "priority": "Low"}
        ]
        
        print(f"[ProjectScaffolder] Adding {len(starter_tasks)} starter tasks to DB {database_id}...")
        for task in starter_tasks:
            payload = {
                "parent": {"database_id": database_id},
                "properties": {
                    "Name": {"title": [{"text": {"content": task["name"]}}]},
                    "Status": {"status": {"name": task["status"]}},
                    "Priority": {"select": {"name": task["priority"]}}
                }
            }
            try:
                requests.post(url, headers=headers, json=payload, timeout=10)
            except Exception as e:
                print(f"[ProjectScaffolder] Failed to add starter task '{task['Name']}': {e}")
