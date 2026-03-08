"""GitHub tool for repository management.

Uses the gh CLI for GitHub operations. Requires GITHUB_TOKEN or gh auth login.

Available operations:
- List/create/close issues
- List/view/merge pull requests
- View repository info
- Create releases
- Manage labels
"""

import json
import logging
import os
import subprocess
from typing import Optional

from tools.registry import registry

logger = logging.getLogger(__name__)


def check_github_requirements() -> bool:
    """Check if GitHub token is available."""
    return bool(os.getenv("GITHUB_TOKEN") or os.getenv("GITHUB_API_KEY"))


def _run_gh_command(args: list, timeout: int = 30) -> dict:
    """Run a gh CLI command and return the result."""
    # Set up environment with token
    env = os.environ.copy()
    token = os.getenv("GITHUB_TOKEN") or os.getenv("GITHUB_API_KEY")
    if token:
        env["GH_TOKEN"] = token
    
    try:
        result = subprocess.run(
            ["gh"] + args,
            capture_output=True,
            text=True,
            timeout=timeout,
            env=env,
        )
        return {
            "output": result.stdout.strip(),
            "error": result.stderr.strip() if result.returncode != 0 else None,
            "returncode": result.returncode,
        }
    except subprocess.TimeoutExpired:
        return {"output": "", "error": "Command timed out", "returncode": 124}
    except FileNotFoundError:
        return {"output": "", "error": "gh CLI not found. Install with: brew install gh", "returncode": 1}
    except Exception as e:
        return {"output": "", "error": str(e), "returncode": 1}


def github_repo(action: str, repo: str, title: str = None, body: str = None, 
                number: int = None, labels: str = None, task_id: str = None) -> str:
    """
    GitHub repository operations.
    
    Actions:
    - view: View repository info
    - issues: List issues
    - issue_create: Create a new issue (requires title)
    - issue_view: View a specific issue (requires number)
    - issue_close: Close an issue (requires number)
    - prs: List pull requests
    - pr_view: View a specific PR (requires number)
    - pr_merge: Merge a PR (requires number)
    - labels: List labels
    - label_create: Create a label (requires title, optional: body for description)
    """
    try:
        if action == "view":
            result = _run_gh_command(["repo", "view", repo, "--json", "name,description,url,stargazerCount,forkCount,hasIssuesEnabled"])
            if result.get("error"):
                return json.dumps({"error": result["error"]})
            try:
                return result["output"]
            except:
                return json.dumps({"output": result["output"]})
                
        elif action == "issues":
            result = _run_gh_command(["issue", "list", "-R", repo, "--json", "number,title,state,author,labels", "--limit", "20"])
            if result.get("error"):
                return json.dumps({"error": result["error"]})
            return result["output"] or json.dumps({"issues": []})
            
        elif action == "issue_create":
            if not title:
                return json.dumps({"error": "title parameter required for issue_create"})
            args = ["issue", "create", "-R", repo, "--title", title]
            if body:
                args.extend(["--body", body])
            else:
                args.extend(["--body", ""])
            if labels:
                args.extend(["--label", labels])
            result = _run_gh_command(args)
            if result.get("error"):
                return json.dumps({"error": result["error"]})
            return json.dumps({"success": True, "message": result["output"]})
            
        elif action == "issue_view":
            if not number:
                return json.dumps({"error": "number parameter required for issue_view"})
            result = _run_gh_command(["issue", "view", str(number), "-R", repo, "--json", "number,title,body,state,author,labels,comments"])
            if result.get("error"):
                return json.dumps({"error": result["error"]})
            return result["output"]
            
        elif action == "issue_close":
            if not number:
                return json.dumps({"error": "number parameter required for issue_close"})
            result = _run_gh_command(["issue", "close", str(number), "-R", repo])
            if result.get("error"):
                return json.dumps({"error": result["error"]})
            return json.dumps({"success": True, "message": f"Issue #{number} closed"})
            
        elif action == "prs":
            result = _run_gh_command(["pr", "list", "-R", repo, "--json", "number,title,state,author,headRefName"])
            if result.get("error"):
                return json.dumps({"error": result["error"]})
            return result["output"] or json.dumps({"prs": []})
            
        elif action == "pr_view":
            if not number:
                return json.dumps({"error": "number parameter required for pr_view"})
            result = _run_gh_command(["pr", "view", str(number), "-R", repo, "--json", "number,title,body,state,author,mergeable,commits"])
            if result.get("error"):
                return json.dumps({"error": result["error"]})
            return result["output"]
            
        elif action == "pr_merge":
            if not number:
                return json.dumps({"error": "number parameter required for pr_merge"})
            result = _run_gh_command(["pr", "merge", str(number), "-R", repo, "--merge"])
            if result.get("error"):
                return json.dumps({"error": result["error"]})
            return json.dumps({"success": True, "message": f"PR #{number} merged"})
            
        elif action == "labels":
            result = _run_gh_command(["label", "list", "-R", repo, "--json", "name,description,color"])
            if result.get("error"):
                return json.dumps({"error": result["error"]})
            return result["output"] or json.dumps({"labels": []})
            
        elif action == "label_create":
            if not title:
                return json.dumps({"error": "title parameter required for label_create"})
            args = ["label", "create", title, "-R", repo]
            if body:
                args.extend(["--description", body])
            result = _run_gh_command(args)
            if result.get("error"):
                return json.dumps({"error": result["error"]})
            return json.dumps({"success": True, "message": f"Label '{title}' created"})
            
        else:
            return json.dumps({"error": f"Unknown action: {action}. Available: view, issues, issue_create, issue_view, issue_close, prs, pr_view, pr_merge, labels, label_create"})
            
    except Exception as e:
        logger.exception(f"GitHub tool error: {e}")
        return json.dumps({"error": str(e)})


# Register the tool
GITHUB_REPO_SCHEMA = {
    "name": "github_repo",
    "description": """GitHub repository operations using the gh CLI.

Actions:
- view: View repository info
- issues: List open issues
- issue_create: Create a new issue (requires 'title', optional 'body' and 'labels')
- issue_view: View issue details (requires 'number')
- issue_close: Close an issue (requires 'number')
- prs: List pull requests
- pr_view: View PR details (requires 'number')
- pr_merge: Merge a PR (requires 'number')
- labels: List repository labels
- label_create: Create a label (requires 'title', optional 'body' for description)

Examples:
- {"action": "view", "repo": "owner/repo"}
- {"action": "issues", "repo": "owner/repo"}
- {"action": "issue_create", "repo": "owner/repo", "title": "Bug report", "body": "Details..."}
- {"action": "issue_close", "repo": "owner/repo", "number": 42}""",
    "parameters": {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": ["view", "issues", "issue_create", "issue_view", "issue_close", "prs", "pr_view", "pr_merge", "labels", "label_create"],
                "description": "The GitHub action to perform"
            },
            "repo": {
                "type": "string",
                "description": "Repository in owner/repo format (e.g., 'hdresearch/not_a_calculator')"
            },
            "title": {
                "type": "string",
                "description": "Title for issue_create or label_create"
            },
            "body": {
                "type": "string",
                "description": "Body/description for issue_create or label_create"
            },
            "number": {
                "type": "integer",
                "description": "Issue or PR number for view/close/merge actions"
            },
            "labels": {
                "type": "string",
                "description": "Comma-separated labels for issue_create"
            }
        },
        "required": ["action", "repo"]
    }
}

registry.register(
    name="github_repo",
    toolset="github",
    schema=GITHUB_REPO_SCHEMA,
    handler=lambda args, **kw: github_repo(
        action=args.get("action", ""),
        repo=args.get("repo", ""),
        title=args.get("title"),
        body=args.get("body"),
        number=args.get("number"),
        labels=args.get("labels"),
        task_id=kw.get("task_id"),
    ),
    check_fn=check_github_requirements,
    requires_env=["GITHUB_TOKEN"],
)
