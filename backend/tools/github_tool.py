import requests
from backend.config import config

GITHUB_TOKEN = config.GITHUB_TOKEN
GITHUB_API_URL = "https://api.github.com"
DEFAULT_TIMEOUT = 10.0

def _get_headers():
    return {
        "Authorization": f"token {GITHUB_TOKEN}",
        "Accept": "application/vnd.github.v3+json"
    }


def _get_authenticated_owner():
    """Return login for the current token owner, or None if unavailable."""
    if not GITHUB_TOKEN:
        return None

    try:
        response = requests.get(f"{GITHUB_API_URL}/user", headers=_get_headers(), timeout=DEFAULT_TIMEOUT)
        if response.status_code >= 400:
            return None
        return response.json().get("login")
    except Exception:
        return None

def create_issue(owner: str, repo: str, title: str, body: str = ""):
    if not GITHUB_TOKEN:
        return {"success": False, "data": {}, "error": "GITHUB_TOKEN_MISSING"}

    payload = {"title": title, "body": body}

    requested_owner = owner or _get_authenticated_owner() or ""
    if not requested_owner:
        return {"success": False, "data": {}, "error": "GITHUB_OWNER_MISSING"}

    url = f"{GITHUB_API_URL}/repos/{requested_owner}/{repo}/issues"
    
    try:
        response = requests.post(url, headers=_get_headers(), json=payload, timeout=DEFAULT_TIMEOUT)

        # Common user-task mismatch: owner in prompt differs from token owner.
        if response.status_code == 404:
            fallback_owner = _get_authenticated_owner()
            if fallback_owner and fallback_owner != requested_owner:
                fallback_url = f"{GITHUB_API_URL}/repos/{fallback_owner}/{repo}/issues"
                fallback_response = requests.post(fallback_url, headers=_get_headers(), json=payload, timeout=DEFAULT_TIMEOUT)
                if fallback_response.status_code < 400:
                    return {"success": True, "data": fallback_response.json(), "error": None}

        if response.status_code >= 400:
            return {"success": False, "data": {}, "error": f"GITHUB_API_ERROR:{response.status_code}"}
        return {"success": True, "data": response.json(), "error": None}
    except requests.exceptions.Timeout:
        return {"success": False, "data": {}, "error": "GITHUB_TIMEOUT"}
    except Exception as e:
        return {"success": False, "data": {}, "error": f"GITHUB_UNEXPECTED_ERROR:{str(e)}"}

def create_repo(name: str, description: str = "", private: bool = True):
    if not GITHUB_TOKEN:
         return {"success": False, "data": {}, "error": "GITHUB_TOKEN_MISSING"}

    url = f"{GITHUB_API_URL}/user/repos"
    payload = {
        "name": name,
        "description": description,
        "private": private,
        "auto_init": True
    }
    
    try:
        response = requests.post(url, headers=_get_headers(), json=payload, timeout=DEFAULT_TIMEOUT)

        # Idempotent behavior: if repo already exists for this account, return it as success.
        if response.status_code == 422:
            owner = _get_authenticated_owner()
            if owner:
                get_url = f"{GITHUB_API_URL}/repos/{owner}/{name}"
                existing = requests.get(get_url, headers=_get_headers(), timeout=DEFAULT_TIMEOUT)
                if existing.status_code < 400:
                    return {"success": True, "data": existing.json(), "error": None}

        if response.status_code >= 400:
            return {"success": False, "data": {}, "error": f"GITHUB_API_ERROR:{response.status_code}"}
        return {"success": True, "data": response.json(), "error": None}
    except requests.exceptions.Timeout:
        return {"success": False, "data": {}, "error": "GITHUB_TIMEOUT"}
    except Exception as e:
        return {"success": False, "data": {}, "error": f"GITHUB_UNEXPECTED_ERROR:{str(e)}"}

def get_repository_issues(owner: str, repo: str, state: str = "open"):
    if not GITHUB_TOKEN:
         return {"success": False, "data": {}, "error": "GITHUB_TOKEN_MISSING"}

    url = f"{GITHUB_API_URL}/repos/{owner}/{repo}/issues?state={state}"
    
    try:
        response = requests.get(url, headers=_get_headers(), timeout=DEFAULT_TIMEOUT)
        if response.status_code >= 400:
            return {"success": False, "data": {}, "error": f"GITHUB_API_ERROR:{response.status_code}"}
        return {"success": True, "data": response.json(), "error": None}
    except requests.exceptions.Timeout:
        return {"success": False, "data": {}, "error": "GITHUB_TIMEOUT"}
    except Exception as e:
         return {"success": False, "data": {}, "error": f"GITHUB_UNEXPECTED_ERROR:{str(e)}"}
