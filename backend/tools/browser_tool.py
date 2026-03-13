from urllib.parse import quote_plus

import requests
from playwright.sync_api import sync_playwright
from backend.config import config


def _normalize_search_query(query: str) -> str:
    cleaned = " ".join((query or "").split())

    # Demo notes often include explanatory prose that hurts search quality.
    lowered = cleaned.lower()
    marker = "what it demonstrates:"
    if marker in lowered:
        cleaned = cleaned[:lowered.index(marker)].strip()

    return cleaned


def _search_with_tavily(query: str):
    payload = {
        "api_key": config.TAVILY_API_KEY,
        "query": query,
        "search_depth": "advanced",
        "max_results": 5,
        "include_answer": False,
        "include_raw_content": False,
    }

    response = requests.post("https://api.tavily.com/search", json=payload, timeout=20)
    if response.status_code >= 400:
        return {
            "success": False,
            "data": {},
            "error": f"TAVILY_API_ERROR:{response.status_code}:{response.text[:200]}",
        }

    data = response.json()
    items = data.get("results", [])
    results = []

    for item in items[:5]:
        if not isinstance(item, dict):
            continue

        results.append({
            "title": item.get("title", ""),
            "snippet": item.get("content", ""),
            "link": item.get("url", ""),
        })

    return {
        "success": True,
        "data": {"query": query, "results": results, "provider": "tavily"},
        "error": None,
    }


def _search_with_duckduckgo(query: str):
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        try:
            page.goto(
                f"https://html.duckduckgo.com/html/?q={quote_plus(query)}",
                wait_until="networkidle",
                timeout=30000,
            )

            results = []
            result_cards = page.locator(".result")
            card_count = min(result_cards.count(), 5)

            for i in range(card_count):
                card = result_cards.nth(i)

                title = ""
                snippet = ""
                link = ""

                title_locator = card.locator("a.result__a").first
                if title_locator.count() > 0:
                    title = title_locator.inner_text().strip()
                    href = title_locator.get_attribute("href")
                    link = href.strip() if isinstance(href, str) else ""

                snippet_locator = card.locator(".result__snippet").first
                if snippet_locator.count() > 0:
                    snippet = snippet_locator.inner_text().strip()

                url_locator = card.locator(".result__url").first
                if not link and url_locator.count() > 0:
                    link = url_locator.inner_text().strip()

                if not any([title, snippet, link]):
                    continue

                results.append({
                    "title": title,
                    "snippet": snippet,
                    "link": link,
                })

            return {
                "success": True,
                "data": {"query": query, "results": results, "provider": "duckduckgo"},
                "error": None,
            }
        except Exception as e:
            return {"success": False, "data": {}, "error": f"Search failed: {str(e)}"}
        finally:
            browser.close()

def open_url_and_extract_text(url: str):
    """
    Opens a URL and extracts the visible text from the page.
    """
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        try:
            page.goto(url, wait_until="networkidle", timeout=30000)
            text_content = page.locator("body").inner_text()
            return {"success": True, "data": {"url": url, "content": text_content[:5000]}, "error": None}
        except Exception as e:
            return {"success": False, "data": {}, "error": f"Failed to load {url}: {str(e)}"}
        finally:
            browser.close()

def search_and_extract(query: str):
    """
    Performs a web search via Tavily when configured, otherwise DuckDuckGo.
    """
    normalized_query = _normalize_search_query(query)

    if config.TAVILY_API_KEY:
        tavily_result = _search_with_tavily(normalized_query)
        if tavily_result.get("success"):
            return tavily_result

    return _search_with_duckduckgo(normalized_query)

def fill_form_and_submit(url: str, form_data: dict, submit_selector: str):
    """
    Navigates to a page, fills a form, and clicks a submit button.
    Example `form_data`: {"#username": "john", "#password": "secret"}
    """
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        try:
            page.goto(url, wait_until="networkidle", timeout=30000)
            
            for selector, value in form_data.items():
                try:
                    # Wait for selector to be visible before filling
                    page.wait_for_selector(selector, state="visible", timeout=5000)
                    page.fill(selector, str(value))
                except Exception as ex:
                    print(f"Selector '{selector}' not found or interactable: {ex}")
                
            page.wait_for_selector(submit_selector, state="visible", timeout=5000)
            page.click(submit_selector)
            page.wait_for_load_state("networkidle", timeout=30000)
            
            return {"success": True, "data": {"new_url": page.url}, "error": None}
        except Exception as e:
            return {"success": False, "data": {}, "error": f"Form submission failed: {str(e)}"}
        finally:
            browser.close()
