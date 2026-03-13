import os
from pathlib import Path
from dotenv import load_dotenv

# Always load env from backend/.env, even when the app is started from project root.
load_dotenv(Path(__file__).resolve().parent / ".env")

class Config:
    DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/notionos")
    NOTION_API_KEY = os.getenv("NOTION_API_KEY", "")
    GITHUB_TOKEN = os.getenv("GITHUB_TOKEN", "")
    GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY", "")      # Gemini (primary)
    GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")          # Groq (fallback)
    TAVILY_API_KEY = os.getenv("TAVILY_API_KEY", "")      # Tavily web search
    NOTION_DATABASE_ID = os.getenv("NOTION_DATABASE_ID", "")

config = Config()
