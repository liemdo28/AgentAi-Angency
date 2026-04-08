"""
Dev Agent — AI-powered developer that can read, analyze, write, and deploy code.

Uses Claude API for code generation (always Claude, never Ollama for code quality).
Can interact with local project files and git.
"""

from __future__ import annotations

import logging
import os
import subprocess
from pathlib import Path
from typing import Any, Dict, List

from core.agents.base import BaseAgent
from core.agents.roles import ROLE_DEFINITIONS

logger = logging.getLogger("agents.dev")

MASTER_DIR = Path(os.environ.get(
    "MASTER_PROJECT_DIR",
    Path(__file__).resolve().parent.parent.parent.parent / "Master"
))

# Project folder mapping (id → actual folder name)
PROJECT_FOLDERS = {
    "agentai-agency": "agentai-agency",
    "BakudanWebsite_Sub": "BakudanWebsite_Sub",
    "BakudanWebsite_Sub2": "BakudanWebsite_Sub2",
    "RawWebsite": "RawWebsite",
    "dashboard.bakudanramen.com": "dashboard.bakudanramen.com",
    "growth-dashboard": "growth-dashboard",
    "integration-full": "integration-full",
    "review-dashboard": "review-dashboard",
    "review-management-mcp": "review-management-mcp",
    "review-system": "review-system",
}


class DevAgent(BaseAgent):
    """AI Developer agent — reads/writes code, runs git, deploys."""

    _role = ROLE_DEFINITIONS.get("dev-agent", {})
    description = _role.get("system_prompt", "Senior full-stack developer agent")
    title = _role.get("title", "Dev Agent")
    responsibilities = _role.get("responsibilities", [])
    agent_tools = _role.get("tools", [])
    kpis = _role.get("kpis", [])
    model = _role.get("model", "claude-sonnet-4-20250514")
    level = _role.get("level", "specialist")

    def run(self, task: Dict[str, Any]) -> Dict[str, Any]:
        """Execute a dev task based on the action in context_json."""
        context = task.get("context_json", {})
        if isinstance(context, str):
            import json
            try:
                context = json.loads(context)
            except Exception:
                context = {}

        action = context.get("action", "review_code")
        project_id = context.get("project_id", "agentai-agency")

        try:
            if action == "review_code":
                return self._review_code(project_id, task.get("description", ""))
            elif action == "analyze_structure":
                return self._analyze_structure(project_id)
            elif action == "write_code":
                return self._write_code(project_id, task.get("description", ""))
            elif action == "fix_bug":
                return self._fix_bug(project_id, task.get("description", ""))
            elif action == "git_status":
                return self._git_status(project_id)
            elif action == "deploy":
                return self._deploy(project_id)
            else:
                return self._review_code(project_id, task.get("description", ""))
        except Exception as exc:
            logger.exception("Dev agent error: %s", exc)
            return {"status": "error", "error": str(exc)}

    # ── Tools ─────────────────────────────────────────────────────────

    def _get_project_path(self, project_id: str) -> Path:
        folder = PROJECT_FOLDERS.get(project_id, project_id)
        return MASTER_DIR / folder

    def _read_project_tree(self, project_path: Path, max_files: int = 50) -> List[str]:
        """Get project file listing (excluding common ignores)."""
        ignores = {".git", "node_modules", "__pycache__", ".venv", "venv", "dist", ".cache", ".next"}
        files = []
        for f in sorted(project_path.rglob("*")):
            if f.is_file() and not any(ig in f.parts for ig in ignores):
                rel = f.relative_to(project_path)
                files.append(str(rel))
                if len(files) >= max_files:
                    break
        return files

    def _read_file(self, filepath: Path, max_lines: int = 200) -> str:
        """Read file content, truncated."""
        try:
            content = filepath.read_text(encoding="utf-8", errors="replace")
            lines = content.split("\n")
            if len(lines) > max_lines:
                return "\n".join(lines[:max_lines]) + f"\n... ({len(lines) - max_lines} more lines)"
            return content
        except Exception as e:
            return f"[Error reading file: {e}]"

    def _git_run(self, project_path: Path, *args: str) -> str:
        """Run a git command in the project directory."""
        try:
            result = subprocess.run(
                ["git"] + list(args),
                cwd=str(project_path),
                capture_output=True, text=True, timeout=10,
            )
            return result.stdout.strip() if result.returncode == 0 else result.stderr.strip()
        except Exception as e:
            return f"[Git error: {e}]"

    # ── Actions ───────────────────────────────────────────────────────

    def _review_code(self, project_id: str, description: str) -> dict:
        """Review project code using Claude."""
        project_path = self._get_project_path(project_id)
        if not project_path.exists():
            return {"status": "error", "output": f"Project {project_id} not found at {project_path}"}

        # Gather context
        files = self._read_project_tree(project_path)
        key_files_content = {}

        # Read key files for context
        for fname in ["README.md", "package.json", "requirements.txt", "index.html", "app.py", "main.py"]:
            fpath = project_path / fname
            if fpath.exists():
                key_files_content[fname] = self._read_file(fpath, max_lines=50)

        # Build prompt for Claude
        prompt = f"""Review the following project: {project_id}

Project structure ({len(files)} files):
{chr(10).join('- ' + f for f in files[:30])}

Key files:
"""
        for fname, content in key_files_content.items():
            prompt += f"\n### {fname}\n```\n{content[:1000]}\n```\n"

        if description:
            prompt += f"\nSpecific review focus: {description}"

        prompt += "\n\nProvide: 1) Project summary 2) Code quality assessment 3) Issues found 4) Recommendations"

        # Call Claude
        from core.orchestrator.executor import AgentExecutor
        executor = AgentExecutor()
        result = executor.router.complete(
            prompt=prompt,
            system=self.description,
            task_type="code",
            description=f"Code review for {project_id}",
        )

        return {
            "status": "done",
            "action": "review_code",
            "project_id": project_id,
            "files_analyzed": len(files),
            "output": result,
        }

    def _analyze_structure(self, project_id: str) -> dict:
        """Analyze project structure without LLM."""
        project_path = self._get_project_path(project_id)
        if not project_path.exists():
            return {"status": "error", "output": f"Project not found: {project_id}"}

        files = self._read_project_tree(project_path, max_files=100)
        branch = self._git_run(project_path, "rev-parse", "--abbrev-ref", "HEAD")
        last_commit = self._git_run(project_path, "log", "-1", "--format=%s (%ar)")
        dirty = bool(self._git_run(project_path, "status", "--porcelain"))

        # Detect tech stack
        tech = []
        if (project_path / "package.json").exists():
            tech.append("Node.js")
        if (project_path / "requirements.txt").exists():
            tech.append("Python")
        if (project_path / "composer.json").exists():
            tech.append("PHP")
        if any(f.endswith(".html") for f in files):
            tech.append("HTML")

        # Count by extension
        ext_counts = {}
        for f in files:
            ext = Path(f).suffix.lower()
            if ext:
                ext_counts[ext] = ext_counts.get(ext, 0) + 1

        return {
            "status": "done",
            "action": "analyze_structure",
            "project_id": project_id,
            "total_files": len(files),
            "tech_stack": tech,
            "branch": branch,
            "last_commit": last_commit,
            "has_uncommitted": dirty,
            "file_extensions": dict(sorted(ext_counts.items(), key=lambda x: -x[1])[:10]),
            "output": f"Project {project_id}: {len(files)} files, tech: {', '.join(tech)}, branch: {branch}",
        }

    def _write_code(self, project_id: str, description: str) -> dict:
        """Generate code using Claude (does NOT auto-write to disk — returns code for review)."""
        project_path = self._get_project_path(project_id)
        files = self._read_project_tree(project_path) if project_path.exists() else []

        prompt = f"""You are working on project: {project_id}
Project files: {', '.join(files[:20])}

Task: {description}

Generate the code needed. Include:
1. File path where each piece of code should go
2. Complete code content
3. Explanation of changes

Format each file as:
### FILE: path/to/file.ext
```language
code here
```
"""
        from core.orchestrator.executor import AgentExecutor
        result = AgentExecutor().router.complete(
            prompt=prompt,
            system=self.description,
            task_type="code",
            description=f"Write code for {project_id}",
        )

        return {
            "status": "done",
            "action": "write_code",
            "project_id": project_id,
            "output": result,
            "note": "Code generated but NOT written to disk. Review and apply manually.",
        }

    def _fix_bug(self, project_id: str, description: str) -> dict:
        """Analyze and suggest a fix for a bug."""
        project_path = self._get_project_path(project_id)
        if not project_path.exists():
            return {"status": "error", "output": f"Project not found: {project_id}"}

        # Get recent git changes for context
        recent_diff = self._git_run(project_path, "diff", "--stat", "HEAD~3..HEAD")
        recent_log = self._git_run(project_path, "log", "--oneline", "-5")

        prompt = f"""You are debugging project: {project_id}

Bug report: {description}

Recent changes:
{recent_diff[:1000]}

Recent commits:
{recent_log}

Analyze the bug and provide:
1. Likely root cause
2. Affected files
3. Suggested fix (with code)
4. How to test the fix
"""
        from core.orchestrator.executor import AgentExecutor
        result = AgentExecutor().router.complete(
            prompt=prompt,
            system=self.description,
            task_type="code",
            description=f"Fix bug in {project_id}",
        )

        return {
            "status": "done",
            "action": "fix_bug",
            "project_id": project_id,
            "output": result,
        }

    def _git_status(self, project_id: str) -> dict:
        """Get git status for a project."""
        project_path = self._get_project_path(project_id)
        if not project_path.exists():
            return {"status": "error", "output": f"Project not found: {project_id}"}

        branch = self._git_run(project_path, "rev-parse", "--abbrev-ref", "HEAD")
        status = self._git_run(project_path, "status", "--short")
        log = self._git_run(project_path, "log", "--oneline", "-5")
        remotes = self._git_run(project_path, "remote", "-v")

        return {
            "status": "done",
            "action": "git_status",
            "project_id": project_id,
            "branch": branch,
            "git_status": status or "(clean)",
            "recent_commits": log,
            "remotes": remotes,
            "output": f"Branch: {branch}\nStatus: {status or 'clean'}\nRecent: {log}",
        }

    def _deploy(self, project_id: str) -> dict:
        """Check if deploy is possible and describe steps (does NOT auto-deploy)."""
        project_path = self._get_project_path(project_id)
        if not project_path.exists():
            return {"status": "error", "output": f"Project not found: {project_id}"}

        # Check for deploy scripts
        deploy_files = []
        for name in ["deploy.sh", "deploy.bat", "Dockerfile", "docker-compose.yml",
                      "vercel.json", "netlify.toml", "wrangler.toml", ".github/workflows"]:
            if (project_path / name).exists():
                deploy_files.append(name)

        has_git_remote = bool(self._git_run(project_path, "remote", "get-url", "origin"))
        dirty = bool(self._git_run(project_path, "status", "--porcelain"))

        return {
            "status": "done",
            "action": "deploy",
            "project_id": project_id,
            "deploy_files_found": deploy_files,
            "has_git_remote": has_git_remote,
            "has_uncommitted_changes": dirty,
            "output": (
                f"Deploy check for {project_id}:\n"
                f"- Deploy configs: {', '.join(deploy_files) or 'none found'}\n"
                f"- Git remote: {'yes' if has_git_remote else 'no'}\n"
                f"- Uncommitted changes: {'yes' if dirty else 'no'}\n"
                f"NOTE: Auto-deploy not executed. Review and deploy manually."
            ),
        }
