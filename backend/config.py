import os
from pathlib import Path
from dotenv import load_dotenv

# Always load env from backend/.env, even when the app is started from project root.
load_dotenv(Path(__file__).resolve().parent / ".env")

class Config:
    DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/notionos")
    NOTION_API_KEY = os.getenv("NOTION_API_KEY", "")
    GITHUB_TOKEN = os.getenv("GITHUB_TOKEN", "")
    
    GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")          # Groq (primary)
    GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")      # Gemini (fallback)
    TAVILY_API_KEY = os.getenv("TAVILY_API_KEY", "")      # Tavily web search
    NOTION_DATABASE_ID = os.getenv("NOTION_DATABASE_ID", "")

    NOTION_MCP_ENABLED = os.getenv("NOTION_MCP_ENABLED", "true").lower() == "true"
    NOTION_MCP_MODE = os.getenv("NOTION_MCP_MODE", "hybrid")

config = Config()
