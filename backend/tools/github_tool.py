import requests
import datetime
import base64
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


def _resolve_owner(owner: str):
    return owner or _get_authenticated_owner()


def _repo_exists(owner: str, repo: str) -> bool:
    if not owner or not repo:
        return False
    try:
        url = f"{GITHUB_API_URL}/repos/{owner}/{repo}"
        response = requests.get(url, headers=_get_headers(), timeout=DEFAULT_TIMEOUT)
        return response.status_code < 400
    except Exception:
        return False


def _get_branch_sha(owner: str, repo: str, branch: str):
    ref_url = f"{GITHUB_API_URL}/repos/{owner}/{repo}/git/ref/heads/{branch}"
    response = requests.get(ref_url, headers=_get_headers(), timeout=DEFAULT_TIMEOUT)
    if response.status_code >= 400:
        return None
    return (response.json().get("object") or {}).get("sha")


def _get_repo_default_branch(owner: str, repo: str):
    url = f"{GITHUB_API_URL}/repos/{owner}/{repo}"
    response = requests.get(url, headers=_get_headers(), timeout=DEFAULT_TIMEOUT)
    if response.status_code >= 400:
        return None
    return response.json().get("default_branch")


def _create_branch(owner: str, repo: str, branch: str, base_sha: str):
    ref_url = f"{GITHUB_API_URL}/repos/{owner}/{repo}/git/refs"
    payload = {
        "ref": f"refs/heads/{branch}",
        "sha": base_sha,
    }
    response = requests.post(ref_url, headers=_get_headers(), json=payload, timeout=DEFAULT_TIMEOUT)
    # 422 likely means branch already exists.
    if response.status_code in (201, 422):
        return True
    return False


def _commit_file_to_branch(owner: str, repo: str, branch: str, file_path: str, content: str, commit_message: str):
    encoded_content = base64.b64encode(content.encode("utf-8")).decode("utf-8")
    contents_url = f"{GITHUB_API_URL}/repos/{owner}/{repo}/contents/{file_path}"

    # If file exists in target branch, include SHA for update.
    existing = requests.get(f"{contents_url}?ref={branch}", headers=_get_headers(), timeout=DEFAULT_TIMEOUT)
    payload = {
        "message": commit_message,
        "content": encoded_content,
        "branch": branch,
    }
    if existing.status_code == 200:
        payload["sha"] = existing.json().get("sha")

    response = requests.put(contents_url, headers=_get_headers(), json=payload, timeout=DEFAULT_TIMEOUT)
    if response.status_code >= 400:
        if response.status_code == 422:
            # GitHub returns 422 when the incoming content is identical.
            # Treat as a no-op so reruns can still return an existing PR.
            message = ""
            try:
                message = (response.json() or {}).get("message", "")
            except Exception:
                message = ""
            if "same" in message.lower() or "identical" in message.lower():
                return {
                    "success": True,
                    "data": {"note": "NO_CONTENT_CHANGE"},
                    "error": None,
                }
        return {"success": False, "data": {}, "error": f"GITHUB_API_ERROR:{response.status_code}"}

    return {"success": True, "data": response.json(), "error": None}


def _bootstrap_base_branch(owner: str, repo: str, preferred_branch: str):
    """Create the first commit for empty repositories so PR flow can proceed."""
    bootstrap_path = "docs/.bootstrap.md"
    bootstrap_content = base64.b64encode(
        b"Repository bootstrap commit created by NotionOS."
    ).decode("utf-8")
    contents_url = f"{GITHUB_API_URL}/repos/{owner}/{repo}/contents/{bootstrap_path}"

    payload_with_branch = {
        "message": "chore: bootstrap repository",
        "content": bootstrap_content,
        "branch": preferred_branch,
    }
    response = requests.put(contents_url, headers=_get_headers(), json=payload_with_branch, timeout=DEFAULT_TIMEOUT)
    if response.status_code in (200, 201):
        return True

    payload_default = {
        "message": "chore: bootstrap repository",
        "content": bootstrap_content,
    }
    response_default = requests.put(contents_url, headers=_get_headers(), json=payload_default, timeout=DEFAULT_TIMEOUT)
    return response_default.status_code in (200, 201)


def _get_existing_open_pr(owner: str, repo: str, head_branch: str, base_branch: str):
    pulls_url = f"{GITHUB_API_URL}/repos/{owner}/{repo}/pulls"
    existing_url = f"{pulls_url}?state=open&head={owner}:{head_branch}&base={base_branch}"
    existing_response = requests.get(existing_url, headers=_get_headers(), timeout=DEFAULT_TIMEOUT)
    if existing_response.status_code >= 400:
        return None
    items = existing_response.json() or []
    return items[0] if items else None


def github_open_pr(
    owner: str,
    repo: str,
    title: str,
    body: str = "",
    base_branch: str = "main",
    branch_name: str = "",
    file_path: str = "docs/agent-generated-change.md",
    file_content: str = "",
    commit_message: str = "chore: add agent-generated update",
):
    """Create branch + commit + PR from provided/generated content."""
    if not GITHUB_TOKEN:
        return {"success": False, "data": {}, "error": "GITHUB_TOKEN_MISSING"}

    resolved_owner = _resolve_owner(owner)
    if not resolved_owner:
        return {"success": False, "data": {}, "error": "GITHUB_OWNER_MISSING"}

    # If an invalid owner is supplied (e.g. "agent"), fall back to the token owner.
    if not _repo_exists(resolved_owner, repo):
        authenticated_owner = _get_authenticated_owner()
        if authenticated_owner and _repo_exists(authenticated_owner, repo):
            resolved_owner = authenticated_owner
        else:
            return {"success": False, "data": {}, "error": f"REPO_NOT_FOUND:{resolved_owner}/{repo}"}

    safe_branch = branch_name.strip() if isinstance(branch_name, str) else ""
    safe_branch = safe_branch.rstrip(".,;:)")
    if not safe_branch:
        stamp = datetime.datetime.utcnow().strftime("%Y%m%d%H%M%S")
        safe_branch = f"agent/pr-{stamp}"

    content = file_content.strip() if isinstance(file_content, str) else ""
    if not content:
        content = (
            f"# Agent Generated Change\n\n"
            f"Generated at: {datetime.datetime.utcnow().isoformat()}Z\n\n"
            f"PR Title: {title}\n\n"
            f"PR Body:\n{body or 'No description provided.'}\n"
        )

    try:
        effective_base_branch = base_branch
        base_sha = _get_branch_sha(resolved_owner, repo, effective_base_branch)
        if not base_sha:
            detected_default = _get_repo_default_branch(resolved_owner, repo)
            if detected_default:
                effective_base_branch = detected_default
                base_sha = _get_branch_sha(resolved_owner, repo, effective_base_branch)

        if not base_sha:
            bootstrapped = _bootstrap_base_branch(resolved_owner, repo, effective_base_branch)
            if bootstrapped:
                base_sha = _get_branch_sha(resolved_owner, repo, effective_base_branch)

            if not base_sha:
                detected_default = _get_repo_default_branch(resolved_owner, repo)
                if detected_default and detected_default != effective_base_branch:
                    effective_base_branch = detected_default
                    base_sha = _get_branch_sha(resolved_owner, repo, effective_base_branch)

        if not base_sha:
            return {"success": False, "data": {}, "error": f"BASE_BRANCH_NOT_FOUND:{base_branch}"}

        if not _create_branch(resolved_owner, repo, safe_branch, base_sha):
            return {"success": False, "data": {}, "error": "BRANCH_CREATE_FAILED"}

        commit_res = _commit_file_to_branch(
            resolved_owner,
            repo,
            safe_branch,
            file_path,
            content,
            commit_message,
        )
        if not commit_res["success"]:
            return commit_res

        pulls_url = f"{GITHUB_API_URL}/repos/{resolved_owner}/{repo}/pulls"
        pr_payload = {
            "title": title,
            "body": body,
            "head": safe_branch,
            "base": effective_base_branch,
        }
        pr_response = requests.post(pulls_url, headers=_get_headers(), json=pr_payload, timeout=DEFAULT_TIMEOUT)

        if pr_response.status_code == 422:
            existing_pr = _get_existing_open_pr(resolved_owner, repo, safe_branch, effective_base_branch)
            if existing_pr:
                return {
                    "success": True,
                    "data": {
                        "pull_request": existing_pr,
                        "branch": safe_branch,
                        "base_branch": effective_base_branch,
                        "file_path": file_path,
                        "note": "PR already existed; returned existing open PR.",
                    },
                    "error": None,
                }

        if pr_response.status_code >= 400:
            return {"success": False, "data": {}, "error": f"GITHUB_API_ERROR:{pr_response.status_code}"}

        return {
            "success": True,
            "data": {
                "pull_request": pr_response.json(),
                "branch": safe_branch,
                "base_branch": effective_base_branch,
                "file_path": file_path,
            },
            "error": None,
        }
    except requests.exceptions.Timeout:
        return {"success": False, "data": {}, "error": "GITHUB_TIMEOUT"}
    except Exception as e:
        return {"success": False, "data": {}, "error": f"GITHUB_UNEXPECTED_ERROR:{str(e)}"}


def github_pr_review_summary(owner: str, repo: str, pull_number: int, post_comment: bool = True):
    """Fetch PR diff metadata and optionally post an AI-style review summary checklist."""
    if not GITHUB_TOKEN:
        return {"success": False, "data": {}, "error": "GITHUB_TOKEN_MISSING"}

    resolved_owner = _resolve_owner(owner)
    if not resolved_owner:
        return {"success": False, "data": {}, "error": "GITHUB_OWNER_MISSING"}

    try:
        target_pr_number = int(pull_number or 0)
        if target_pr_number <= 0:
            list_url = f"{GITHUB_API_URL}/repos/{resolved_owner}/{repo}/pulls?state=open&sort=updated&direction=desc&per_page=1"
            list_res = requests.get(list_url, headers=_get_headers(), timeout=DEFAULT_TIMEOUT)
            if list_res.status_code >= 400:
                return {"success": False, "data": {}, "error": f"GITHUB_API_ERROR:{list_res.status_code}"}
            items = list_res.json() or []
            if not items:
                return {"success": False, "data": {}, "error": "NO_OPEN_PULL_REQUESTS"}
            target_pr_number = int(items[0].get("number", 0) or 0)

        pr_url = f"{GITHUB_API_URL}/repos/{resolved_owner}/{repo}/pulls/{target_pr_number}"
        files_url = f"{pr_url}/files"

        pr_res = requests.get(pr_url, headers=_get_headers(), timeout=DEFAULT_TIMEOUT)
        if pr_res.status_code >= 400:
            return {"success": False, "data": {}, "error": f"GITHUB_API_ERROR:{pr_res.status_code}"}

        files_res = requests.get(files_url, headers=_get_headers(), timeout=DEFAULT_TIMEOUT)
        if files_res.status_code >= 400:
            return {"success": False, "data": {}, "error": f"GITHUB_API_ERROR:{files_res.status_code}"}

        pr_data = pr_res.json()
        files = files_res.json() or []

        additions = sum(int(f.get("additions", 0)) for f in files if isinstance(f, dict))
        deletions = sum(int(f.get("deletions", 0)) for f in files if isinstance(f, dict))
        changed = len(files)

        file_lines = []
        for file_item in files[:10]:
            if not isinstance(file_item, dict):
                continue
            name = file_item.get("filename", "unknown")
            status = file_item.get("status", "modified")
            file_lines.append(f"- `{name}` ({status})")

        summary_lines = [
            "## Automated PR Review Summary",
            f"- PR: #{target_pr_number} {pr_data.get('title', '')}",
            f"- Changed files: {changed}",
            f"- Additions: {additions}",
            f"- Deletions: {deletions}",
            "",
            "### Touched Files",
        ]
        summary_lines.extend(file_lines if file_lines else ["- No files returned by API"]) 
        summary_lines.extend([
            "",
            "### Review Checklist",
            "- [ ] Validate core behavior changes manually",
            "- [ ] Confirm error handling and fallback paths",
            "- [ ] Confirm no secrets or credentials are introduced",
            "- [ ] Add or update tests for changed logic",
        ])

        summary_text = "\n".join(summary_lines)
        comment_data = None

        if post_comment:
            comment_url = f"{GITHUB_API_URL}/repos/{resolved_owner}/{repo}/issues/{target_pr_number}/comments"
            comment_res = requests.post(comment_url, headers=_get_headers(), json={"body": summary_text}, timeout=DEFAULT_TIMEOUT)
            if comment_res.status_code >= 400:
                return {"success": False, "data": {}, "error": f"GITHUB_API_ERROR:{comment_res.status_code}"}
            comment_data = comment_res.json()

        return {
            "success": True,
            "data": {
                "pull_request": pr_data,
                "summary": summary_text,
                "comment": comment_data,
            },
            "error": None,
        }
    except requests.exceptions.Timeout:
        return {"success": False, "data": {}, "error": "GITHUB_TIMEOUT"}
    except Exception as e:
        return {"success": False, "data": {}, "error": f"GITHUB_UNEXPECTED_ERROR:{str(e)}"}

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
