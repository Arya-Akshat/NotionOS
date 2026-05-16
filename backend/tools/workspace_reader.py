import logging
import re
from typing import Dict, Any, List
from notion_mcp.client import mcp_client

logger = logging.getLogger(__name__)

class WorkspaceStyleAnalyzer:
    @staticmethod
    async def analyze_workspace_style(task_title: str) -> dict:
        """
        Uses notion-search via mcp_client to read existing pages.
        """
        default_style = {
            "case": "title",
            "uses_emojis": False,
            "avg_word_count": 2,
            "uses_separators": False,
            "separator": None
        }
        
        result = {
            "naming_style": default_style,
            "related_pages": [],
            "prior_similar_projects": [],
            "sample_titles": []
        }
        
        try:
            # Try to fetch generic pages for style
            search_res = await mcp_client.search_pages("")
            if not search_res or not isinstance(search_res, list):
                # if empty string search fails, try searching with task_title
                search_res = await mcp_client.search_pages(task_title)
                
            if not search_res or not isinstance(search_res, list):
                return result
                
            all_pages = []
            titles = []
            
            for page in search_res:
                if not isinstance(page, dict):
                    continue
                page_id = page.get("id")
                url = page.get("url", "")
                
                # Extract title
                title = "Untitled"
                try:
                    props = page.get("properties", {})
                    # Name or Title
                    title_prop = props.get("Name") or props.get("Title")
                    if title_prop and "title" in title_prop and title_prop["title"]:
                        title = title_prop["title"][0]["text"]["content"]
                except Exception:
                    pass
                
                if page_id and title != "Untitled":
                    all_pages.append({"id": page_id, "title": title, "url": url})
                    titles.append(title)
            
            if titles:
                result["sample_titles"] = titles[:10]
                result["naming_style"] = await WorkspaceStyleAnalyzer.detect_naming_style(titles)
                result["related_pages"] = await WorkspaceStyleAnalyzer.find_related_pages(task_title, all_pages)
                
        except Exception as e:
            logger.warning(f"[WorkspaceStyleAnalyzer] Failed to analyze workspace style: {e}")
            
        return result

    @staticmethod
    async def detect_naming_style(titles: list[str]) -> dict:
        """
        Analyzes a list of page titles and returns naming conventions.
        Checks: case style, emoji usage, length, separator chars.
        """
        style = {
            "case": "title",
            "uses_emojis": False,
            "avg_word_count": 2,
            "uses_separators": False,
            "separator": None,
            "emoji": "📄" # default emoji for testing
        }
        
        if not titles:
            return style
            
        lower_count = 0
        title_count = 0
        emoji_count = 0
        total_words = 0
        
        for t in titles:
            # Check emojis (simple check for non-ascii characters at the start or anywhere)
            if any(ord(c) > 127 for c in t):
                emoji_count += 1
                
            clean_t = re.sub(r'[^\w\s]', '', t).strip()
            if not clean_t:
                continue
                
            words = clean_t.split()
            total_words += len(words)
            
            if clean_t.islower():
                lower_count += 1
            elif clean_t.istitle() or (words and words[0].istitle()):
                title_count += 1
                
        style["avg_word_count"] = max(1, total_words // len(titles))
        style["uses_emojis"] = emoji_count > (len(titles) / 3) # If more than 1/3 use emojis
        
        if lower_count > title_count:
            style["case"] = "lower"
        else:
            style["case"] = "title"
            
        # Check separators
        separators = ["-", "/", ":"]
        sep_counts = {s: 0 for s in separators}
        for t in titles:
            for s in separators:
                if s in t:
                    sep_counts[s] += 1
                    
        most_common_sep = max(sep_counts, key=sep_counts.get)
        if sep_counts[most_common_sep] > (len(titles) / 4):
            style["uses_separators"] = True
            style["separator"] = most_common_sep
            
        return style

    @staticmethod
    async def find_related_pages(task_title: str, all_titles: list[dict]) -> list:
        """
        Finds pages whose titles share keywords with the task title.
        """
        related = []
        if not task_title or not all_titles:
            return related
            
        task_words = set(re.sub(r'[^\w\s]', '', task_title.lower()).split())
        stop_words = {"a", "an", "the", "in", "on", "at", "for", "to", "my", "and", "or", "new", "create", "build", "launch", "start"}
        task_keywords = task_words - stop_words
        
        if not task_keywords:
            return related
            
        for page in all_titles:
            title = page.get("title", "")
            title_words = set(re.sub(r'[^\w\s]', '', title.lower()).split())
            if task_keywords & title_words:
                related.append(page)
                
        return related[:5]

    @staticmethod
    def apply_naming_style(name: str, style: dict) -> str:
        """
        Takes a default name like "Project Brief" and converts it
        to match the detected style.
        """
        result = name
        
        case_style = style.get("case", "title")
        if case_style == "lower":
            result = result.lower()
        elif case_style == "title":
            result = result.title()
            
        if style.get("uses_emojis"):
            emoji = style.get("emoji", "📄")
            result = f"{emoji} {result}"
            
        return result
