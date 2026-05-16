import requests
import sys
import os

# Add current dir to path
sys.path.append(os.getcwd())

from config import config

def test_create_repo():
    headers = {
        "Authorization": f"token {config.GITHUB_TOKEN}",
        "Accept": "application/vnd.github.v3+json"
    }
    
    # Try to create a dummy repo
    url = "https://api.github.com/user/repos"
    repo_name = "notionos-auth-test"
    payload = {
        "name": repo_name,
        "description": "Verification of Administration permissions",
        "private": True
    }
    
    print(f"Attempting to create repo: {repo_name}...")
    r = requests.post(url, headers=headers, json=payload)
    
    if r.status_code == 201:
        print(f"✅ SUCCESS! Created repo: {repo_name}")
        # Clean up
        print("Cleaning up...")
        del_url = f"https://api.github.com/repos/Arya-Akshat/{repo_name}"
        requests.delete(del_url, headers=headers)
    else:
        print(f"❌ FAILED! Status: {r.status_code}")
        print(f"Response: {r.text}")

if __name__ == "__main__":
    test_create_repo()
