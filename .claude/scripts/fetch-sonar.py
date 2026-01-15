#!/usr/bin/env python3
"""
Fetch SonarCloud issues with flexible filtering.

Integrates with the git context from main.py to provide:
- Branch-based filtering
- Date-based filtering (createdAfter/createdBefore)
- Commit-aware new code period (sinceLeakPeriod)
- PR filtering

Usage:
    # Basic fetch (uses defaults from sonar.yaml)
    python fetch-sonar.py --project myorg_myproject

    # Filter by branch
    python fetch-sonar.py --project myorg_myproject --branch main

    # Filter by date (issues created after)
    python fetch-sonar.py --project myorg_myproject --since 2025-01-01

    # Filter by relative time
    python fetch-sonar.py --project myorg_myproject --since 24h
    python fetch-sonar.py --project myorg_myproject --since 7d

    # Use git context (auto-detect from current branch)
    python fetch-sonar.py --project myorg_myproject --git-context

    # Pull request mode
    python fetch-sonar.py --project myorg_myproject --pr 123

    # Output curl command only (dry-run)
    python fetch-sonar.py --project myorg_myproject --dry-run

    # Custom output file
    python fetch-sonar.py --project myorg_myproject -o issues.json

Environment:
    SONAR_TOKEN: SonarCloud API token (required)
    SONAR_PROJECT_KEY: Default project key (optional, can override with --project)
"""

import argparse
import json
import os
import re
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlencode

import yaml


# =============================================================================
# CONFIGURATION
# =============================================================================

DEFAULT_CONFIG_PATH = Path(__file__).parent.parent / "config" / "sonar.yaml"
SONARCLOUD_API_URL = "https://sonarcloud.io/api"


def load_config(config_path: Path | None = None) -> dict:
    """Load configuration from sonar.yaml."""
    path = config_path or DEFAULT_CONFIG_PATH
    if path.exists():
        with open(path) as f:
            return yaml.safe_load(f) or {}
    return {}


def get_token() -> str | None:
    """Get SonarCloud token from environment."""
    return os.environ.get("SONAR_TOKEN")


def get_project_key(args_project: str | None, config: dict) -> str | None:
    """Get project key from args, env, or config."""
    if args_project:
        return args_project

    env_key = os.environ.get("SONAR_PROJECT_KEY")
    if env_key:
        return env_key

    # From config (may contain ${VAR} placeholder)
    config_key = config.get("sonarcloud", {}).get("project_key", "")
    if config_key and not config_key.startswith("$"):
        return config_key

    return None


# =============================================================================
# DATE PARSING
# =============================================================================

def parse_date_filter(date_str: str | None) -> str | None:
    """Parse date filter to SonarCloud format (ISO 8601).

    Supports:
    - Relative: 24h, 48h, 7d, 2w, 1m
    - ISO date: 2025-01-15
    - ISO datetime: 2025-01-15T10:30:00
    - ISO with timezone: 2025-01-15T10:30:00+0100

    Returns: ISO 8601 format string for SonarCloud API
    """
    if not date_str:
        return None

    # Handle "none" or "all"
    if date_str.lower() in ("none", "all", "0"):
        return None

    # Try relative duration (24h, 7d, 2w, 1m)
    match = re.match(r'^(\d+)([hdwm])$', date_str.lower())
    if match:
        value = int(match.group(1))
        unit = match.group(2)

        now = datetime.now(timezone.utc)
        if unit == 'h':
            delta = timedelta(hours=value)
        elif unit == 'd':
            delta = timedelta(days=value)
        elif unit == 'w':
            delta = timedelta(weeks=value)
        elif unit == 'm':
            delta = timedelta(days=value * 30)
        else:
            delta = timedelta()

        result_date = now - delta
        # SonarCloud format: YYYY-MM-DDTHH:mm:ss+0000
        return result_date.strftime("%Y-%m-%dT%H:%M:%S+0000")

    # Try ISO date formats
    for fmt in [
        "%Y-%m-%dT%H:%M:%S%z",      # 2025-01-15T10:30:00+0100
        "%Y-%m-%dT%H:%M:%S",        # 2025-01-15T10:30:00
        "%Y-%m-%d",                 # 2025-01-15
    ]:
        try:
            parsed = datetime.strptime(date_str, fmt)
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)
            return parsed.strftime("%Y-%m-%dT%H:%M:%S+0000")
        except ValueError:
            continue

    print(f"Warning: Invalid date format '{date_str}', ignoring", file=sys.stderr)
    return None


# =============================================================================
# GIT CONTEXT INTEGRATION
# =============================================================================

def run_git_command(args: list[str], timeout: int = 30) -> tuple[bool, str]:
    """Execute a git command and return (success, output)."""
    try:
        result = subprocess.run(
            ['git'] + args,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        return result.returncode == 0, result.stdout.strip()
    except Exception as e:
        return False, str(e)


def get_git_context() -> dict:
    """Get current git context for SonarCloud filtering.

    Returns:
        dict with keys:
        - branch: current branch name
        - commit: current commit SHA
        - merge_base: merge base with main/develop
        - merge_base_date: date of merge base commit
    """
    context = {}

    # Current branch
    success, branch = run_git_command(['rev-parse', '--abbrev-ref', 'HEAD'])
    if success and branch != 'HEAD':
        context['branch'] = branch

    # Current commit
    success, commit = run_git_command(['rev-parse', 'HEAD'])
    if success:
        context['commit'] = commit

    # Find merge base with main branches
    for base_branch in ['main', 'develop', 'master']:
        success, _ = run_git_command(['rev-parse', '--verify', base_branch])
        if success:
            success, merge_base = run_git_command(['merge-base', 'HEAD', base_branch])
            if success:
                context['merge_base'] = merge_base
                context['parent_branch'] = base_branch

                # Get merge base date
                success, date_str = run_git_command([
                    'show', '-s', '--format=%cI', merge_base
                ])
                if success:
                    context['merge_base_date'] = date_str
                break

    return context


# =============================================================================
# URL BUILDING
# =============================================================================

def build_issues_url(
    project_key: str,
    branch: str | None = None,
    pull_request: str | None = None,
    created_after: str | None = None,
    created_before: str | None = None,
    since_leak_period: bool = False,
    statuses: list[str] | None = None,
    types: list[str] | None = None,
    severities: list[str] | None = None,
    resolved: bool | None = None,
    page_size: int = 500,
    page: int = 1,
    extra_params: dict | None = None,
) -> str:
    """Build SonarCloud API URL for issues search.

    Args:
        project_key: SonarCloud project key (org_repo format)
        branch: Branch name to filter
        pull_request: PR number (alternative to branch)
        created_after: ISO date string (YYYY-MM-DDTHH:mm:ss+0000)
        created_before: ISO date string
        since_leak_period: Use new code period (True/False)
        statuses: List of statuses (OPEN, CONFIRMED, REOPENED, RESOLVED, CLOSED)
        types: List of types (BUG, CODE_SMELL, VULNERABILITY)
        severities: List of severities (BLOCKER, CRITICAL, MAJOR, MINOR, INFO)
        resolved: Filter resolved (True) or unresolved (False) issues
        page_size: Number of results per page (max 500)
        page: Page number
        extra_params: Additional parameters to include

    Returns:
        Complete URL for curl
    """
    params = {
        "projectKeys": project_key,
        "ps": min(page_size, 500),
        "p": page,
    }

    # Branch or PR (mutually exclusive)
    if pull_request:
        params["pullRequest"] = pull_request
    elif branch:
        params["branch"] = branch

    # Date filters
    if created_after:
        params["createdAfter"] = created_after
    if created_before:
        params["createdBefore"] = created_before

    # New code period
    if since_leak_period:
        params["sinceLeakPeriod"] = "true"

    # Status filter
    if statuses:
        params["statuses"] = ",".join(statuses)

    # Type filter
    if types:
        params["types"] = ",".join(types)

    # Severity filter
    if severities:
        params["severities"] = ",".join(severities)

    # Resolved filter
    if resolved is not None:
        params["resolved"] = "true" if resolved else "false"

    # Extra params
    if extra_params:
        params.update(extra_params)

    return f"{SONARCLOUD_API_URL}/issues/search?{urlencode(params)}"


def build_hotspots_url(
    project_key: str,
    branch: str | None = None,
    pull_request: str | None = None,
    status: str | None = None,
    page_size: int = 500,
    page: int = 1,
) -> str:
    """Build SonarCloud API URL for security hotspots search.

    Args:
        project_key: SonarCloud project key
        branch: Branch name
        pull_request: PR number
        status: TO_REVIEW, REVIEWED
        page_size: Results per page
        page: Page number

    Returns:
        Complete URL for curl
    """
    params = {
        "projectKey": project_key,
        "ps": min(page_size, 500),
        "p": page,
    }

    if pull_request:
        params["pullRequest"] = pull_request
    elif branch:
        params["branch"] = branch

    if status:
        params["status"] = status

    return f"{SONARCLOUD_API_URL}/hotspots/search?{urlencode(params)}"


def build_curl_command(
    url: str,
    token: str | None = None,
    output_file: str | None = None,
) -> str:
    """Build curl command string.

    Args:
        url: API URL
        token: SonarCloud token (if None, uses $SONAR_TOKEN placeholder)
        output_file: Output file path

    Returns:
        Complete curl command string
    """
    parts = ["curl", "-s"]

    # Authentication
    if token:
        parts.append(f'-u "{token}:"')
    else:
        parts.append('-u "$SONAR_TOKEN:"')

    # URL
    parts.append(f'"{url}"')

    # Output
    if output_file:
        parts.append(f"> {output_file}")

    return " ".join(parts)


# =============================================================================
# FETCH EXECUTION
# =============================================================================

def fetch_issues(url: str, token: str) -> dict | None:
    """Fetch issues from SonarCloud API.

    Returns parsed JSON or None on error.
    """
    try:
        result = subprocess.run(
            ["curl", "-s", "-u", f"{token}:", url],
            capture_output=True,
            text=True,
            timeout=60,
        )

        if result.returncode != 0:
            print(f"Error: curl failed with code {result.returncode}", file=sys.stderr)
            return None

        return json.loads(result.stdout)

    except json.JSONDecodeError as e:
        print(f"Error: Invalid JSON response: {e}", file=sys.stderr)
        return None
    except subprocess.TimeoutExpired:
        print("Error: Request timed out", file=sys.stderr)
        return None
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        return None


def fetch_all_pages(
    project_key: str,
    token: str,
    **kwargs
) -> dict:
    """Fetch all pages of issues (handles pagination).

    Returns combined result with all issues.
    """
    all_issues = []
    all_rules = {}
    all_components = {}
    page = 1
    total = None

    while True:
        url = build_issues_url(project_key, page=page, **kwargs)
        print(f"Fetching page {page}...", file=sys.stderr)

        data = fetch_issues(url, token)
        if not data:
            break

        # First page: get total
        if total is None:
            total = data.get("total", 0)
            print(f"Total issues: {total}", file=sys.stderr)

        # Collect issues
        issues = data.get("issues", [])
        if not issues:
            break

        all_issues.extend(issues)

        # Collect rules and components
        for rule in data.get("rules", []):
            all_rules[rule.get("key")] = rule
        for comp in data.get("components", []):
            all_components[comp.get("key")] = comp

        # Check if more pages
        page_size = data.get("ps", 500)
        if len(all_issues) >= total or len(issues) < page_size:
            break

        page += 1

    return {
        "total": len(all_issues),
        "issues": all_issues,
        "rules": list(all_rules.values()),
        "components": list(all_components.values()),
    }


# =============================================================================
# CLI
# =============================================================================

def main():
    parser = argparse.ArgumentParser(
        description="Fetch SonarCloud issues with flexible filtering",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    # Basic fetch
    python fetch-sonar.py --project myorg_myrepo

    # Filter by branch
    python fetch-sonar.py --project myorg_myrepo --branch feature/foo

    # Filter by date (last 7 days)
    python fetch-sonar.py --project myorg_myrepo --since 7d

    # Filter by absolute date
    python fetch-sonar.py --project myorg_myrepo --since 2025-01-01

    # PR mode
    python fetch-sonar.py --project myorg_myrepo --pr 123

    # Use git context (auto-detect branch and date from merge-base)
    python fetch-sonar.py --project myorg_myrepo --git-context

    # Only show curl command
    python fetch-sonar.py --project myorg_myrepo --dry-run

    # Fetch security hotspots instead
    python fetch-sonar.py --project myorg_myrepo --hotspots

Environment:
    SONAR_TOKEN       API token (required for fetching)
    SONAR_PROJECT_KEY Default project key
        """
    )

    # Required
    parser.add_argument(
        "--project", "-p",
        type=str,
        default=None,
        help="SonarCloud project key (org_repo format)"
    )

    # Branch/PR filtering
    parser.add_argument(
        "--branch", "-b",
        type=str,
        default=None,
        help="Filter by branch name"
    )
    parser.add_argument(
        "--pr",
        type=str,
        default=None,
        help="Filter by pull request number"
    )

    # Date filtering
    parser.add_argument(
        "--since",
        type=str,
        default=None,
        help="Filter issues created after date. Supports: 24h, 7d, 2w, 1m, or ISO date"
    )
    parser.add_argument(
        "--until",
        type=str,
        default=None,
        help="Filter issues created before date"
    )
    parser.add_argument(
        "--new-code", "--leak-period",
        action="store_true",
        help="Use SonarCloud's 'new code period' (sinceLeakPeriod=true)"
    )

    # Git context
    parser.add_argument(
        "--git-context", "-g",
        action="store_true",
        help="Use current git context (auto-detect branch and merge-base date)"
    )

    # Type/severity filtering
    parser.add_argument(
        "--types", "-t",
        type=str,
        default=None,
        help="Comma-separated types: BUG,CODE_SMELL,VULNERABILITY"
    )
    parser.add_argument(
        "--severities", "-s",
        type=str,
        default=None,
        help="Comma-separated severities: BLOCKER,CRITICAL,MAJOR,MINOR,INFO"
    )
    parser.add_argument(
        "--statuses",
        type=str,
        default="OPEN,CONFIRMED,REOPENED",
        help="Comma-separated statuses (default: OPEN,CONFIRMED,REOPENED)"
    )
    parser.add_argument(
        "--resolved",
        type=str,
        choices=["true", "false"],
        default=None,
        help="Filter resolved (true) or unresolved (false) issues"
    )

    # Output
    parser.add_argument(
        "--output", "-o",
        type=str,
        default="issues.json",
        help="Output file path (default: issues.json)"
    )
    parser.add_argument(
        "--dry-run", "-n",
        action="store_true",
        help="Only print curl command, don't execute"
    )

    # Hotspots
    parser.add_argument(
        "--hotspots",
        action="store_true",
        help="Fetch security hotspots instead of issues"
    )

    # Pagination
    parser.add_argument(
        "--page-size",
        type=int,
        default=500,
        help="Results per page (max 500)"
    )
    parser.add_argument(
        "--all-pages",
        action="store_true",
        help="Fetch all pages (may take time for large projects)"
    )

    args = parser.parse_args()

    # Load config
    config = load_config()
    defaults = config.get("sonarcloud", {}).get("defaults", {})

    # Get project key
    project_key = get_project_key(args.project, config)
    if not project_key:
        print("Error: Project key required. Use --project or set SONAR_PROJECT_KEY", file=sys.stderr)
        sys.exit(1)

    # Get token
    token = get_token()
    if not token and not args.dry_run:
        print("Error: SONAR_TOKEN environment variable required", file=sys.stderr)
        sys.exit(1)

    # Process git context
    branch = args.branch
    created_after = parse_date_filter(args.since)

    if args.git_context:
        git_ctx = get_git_context()
        print(f"Git context: {json.dumps(git_ctx, indent=2)}", file=sys.stderr)

        if not branch and git_ctx.get("branch"):
            branch = git_ctx["branch"]
            print(f"Using git branch: {branch}", file=sys.stderr)

        if not created_after and git_ctx.get("merge_base_date"):
            # Use merge base date as createdAfter
            created_after = parse_date_filter(git_ctx["merge_base_date"])
            print(f"Using merge-base date: {created_after}", file=sys.stderr)

    # Apply defaults from config
    statuses = args.statuses.split(",") if args.statuses else defaults.get("statuses", "OPEN,CONFIRMED,REOPENED").split(",")
    types = args.types.split(",") if args.types else (defaults.get("types", "").split(",") if defaults.get("types") else None)
    severities = args.severities.split(",") if args.severities else None
    resolved = True if args.resolved == "true" else (False if args.resolved == "false" else None)

    # Build URL
    if args.hotspots:
        url = build_hotspots_url(
            project_key=project_key,
            branch=branch,
            pull_request=args.pr,
            page_size=args.page_size,
        )
    else:
        url = build_issues_url(
            project_key=project_key,
            branch=branch,
            pull_request=args.pr,
            created_after=created_after,
            created_before=parse_date_filter(args.until),
            since_leak_period=args.new_code,
            statuses=statuses,
            types=types if types and types[0] else None,
            severities=severities,
            resolved=resolved,
            page_size=args.page_size,
        )

    # Build curl command
    curl_cmd = build_curl_command(url, output_file=args.output if args.dry_run else None)

    # Dry run: just print
    if args.dry_run:
        print("\n# Curl command:")
        print(curl_cmd)
        print("\n# URL breakdown:")
        print(f"  Base: {SONARCLOUD_API_URL}/{'hotspots' if args.hotspots else 'issues'}/search")
        print(f"  Project: {project_key}")
        if branch:
            print(f"  Branch: {branch}")
        if args.pr:
            print(f"  PR: {args.pr}")
        if created_after:
            print(f"  Created After: {created_after}")
        if args.new_code:
            print(f"  Since Leak Period: true")
        print(f"  Statuses: {','.join(statuses)}")
        if types and types[0]:
            print(f"  Types: {','.join(types)}")
        if severities:
            print(f"  Severities: {','.join(severities)}")
        return

    # Execute fetch
    print(f"Fetching issues from SonarCloud...", file=sys.stderr)
    print(f"Project: {project_key}", file=sys.stderr)
    if branch:
        print(f"Branch: {branch}", file=sys.stderr)
    if created_after:
        print(f"Since: {created_after}", file=sys.stderr)

    if args.all_pages:
        # Fetch all pages
        data = fetch_all_pages(
            project_key=project_key,
            token=token,
            branch=branch,
            pull_request=args.pr,
            created_after=created_after,
            created_before=parse_date_filter(args.until),
            since_leak_period=args.new_code,
            statuses=statuses,
            types=types if types and types[0] else None,
            severities=severities,
            resolved=resolved,
            page_size=args.page_size,
        )
    else:
        # Single page
        data = fetch_issues(url, token)

    if not data:
        print("Error: Failed to fetch issues", file=sys.stderr)
        sys.exit(1)

    # Write output
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

    print(f"\nOutput written to: {output_path}", file=sys.stderr)
    print(f"Total issues: {data.get('total', len(data.get('issues', [])))}", file=sys.stderr)

    # Summary by severity
    issues = data.get("issues", [])
    by_severity = {}
    for issue in issues:
        sev = issue.get("severity", "UNKNOWN")
        by_severity[sev] = by_severity.get(sev, 0) + 1

    if by_severity:
        print("\nBy severity:", file=sys.stderr)
        for sev in ["BLOCKER", "CRITICAL", "MAJOR", "MINOR", "INFO"]:
            if sev in by_severity:
                print(f"  {sev}: {by_severity[sev]}", file=sys.stderr)


if __name__ == "__main__":
    main()
