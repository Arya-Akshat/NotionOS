import asyncio
import os
from typing import Any, Dict, Optional
from mcp.client.stdio import stdio_client
from mcp.client.session import ClientSession
from mcp import StdioServerParameters
from config import config
from contextlib import AsyncExitStack

class MCPClient:
    def __init__(self):
        # Using the local node_modules install via npx
        env = os.environ.copy()
        # Ensure NOTION_API_KEY/TOKEN is available for the MCP server
        if config.NOTION_API_KEY:
            env["NOTION_API_KEY"] = config.NOTION_API_KEY
            env["NOTION_TOKEN"] = config.NOTION_API_KEY

        self.server_params = StdioServerParameters(
            command="npx",
            args=["-y", "@notionhq/notion-mcp-server"],
            env=env
        )
        self._exit_stack = None
        self._session: Optional[ClientSession] = None
        self._reconnect_lock = asyncio.Lock()

    async def connect(self):
        if not config.NOTION_MCP_ENABLED:
            print("[MCP] MCP is explicitly disabled in config.")
            return

        async with self._reconnect_lock:
            if self._session:
                return  # already connected

            print("[MCP] Establishing connection to Notion MCP server...")
            try:
                self._exit_stack = AsyncExitStack()
                read, write = await self._exit_stack.enter_async_context(stdio_client(self.server_params))
                
                self._session = await self._exit_stack.enter_async_context(ClientSession(read, write))
                await self._session.initialize()
                print("[MCP] Successfully connected to Notion MCP Server.")
            except Exception as e:
                print(f"[MCP] Failed to connect: {e}")
                await self.disconnect()
                raise

    async def disconnect(self):
        print("[MCP] Disconnecting...")
        if self._exit_stack:
            try:
                await self._exit_stack.aclose()
            except Exception as e:
                print(f"[MCP] Error during disconnect: {e}")
        self._exit_stack = None
        self._session = None

    async def invoke_tool(self, name: str, arguments: Dict[str, Any]) -> Any:
        if not self._session:
            await self.connect()
        try:
            result = await self._session.call_tool(name, arguments)
            # Extract content from CallToolResult
            if hasattr(result, "content") and result.content:
                text = result.content[0].text
                try:
                    return json.loads(text)
                except:
                    return text
            return result
        except Exception as e:
            print(f"[MCP] Tool '{name}' failed: {e}. Attempting reconnect...")
            await self.disconnect()
            await self.connect()
            result = await self._session.call_tool(name, arguments)
            if hasattr(result, "content") and result.content:
                text = result.content[0].text
                try:
                    return json.loads(text)
                except:
                    return text
            return result

    # -------------------------------------------------------------------------
    # Notion operations explicitly mapped as requested
    # -------------------------------------------------------------------------
    async def fetch_page(self, page_id: str):
        return await self.invoke_tool("API-retrieve-a-page", {"page_id": page_id})

    async def update_page(self, page_id: str, properties: dict):
        return await self.invoke_tool("API-patch-page", {"page_id": page_id, "properties": properties})

    async def append_blocks(self, page_id: str, children: list):
        return await self.invoke_tool("API-patch-block-children", {"block_id": page_id, "children": children})

    async def query_database(self, database_id: str, query_filter: dict = None, sorts: list = None):
        # Note: The official server uses retrieve-a-database or post-search for database queries depending on version.
        # Given the list, retrieve-a-database might just be metadata. 
        # For now, let's try the most likely one or fallback gracefully.
        args = {"database_id": database_id}
        if query_filter: args["filter"] = query_filter
        if sorts: args["sorts"] = sorts
        return await self.invoke_tool("API-retrieve-a-database", args)

    async def search_pages(self, query: str):
        return await self.invoke_tool("API-post-search", {"query": query})

# Singleton export
mcp_client = MCPClient()
