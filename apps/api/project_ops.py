from __future__ import annotations

import json
from pathlib import Path


def _read_json(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _signal(label: str, value: str, status: str = "ok") -> dict:
    return {"label": label, "value": value, "status": status}


def _action(
    action_id: str,
    title: str,
    description: str,
    prompt: str,
    action_label: str = "Create workflow",
    action_type: str = "workflow",
) -> dict:
    return {
        "id": action_id,
        "title": title,
        "description": description,
        "prompt": prompt,
        "action_label": action_label,
        "action_type": action_type,
    }


def _has_any(project_path: Path, *candidates: str) -> bool:
    return any((project_path / candidate).exists() for candidate in candidates)


def _package_manifest(project_path: Path) -> dict:
    package_json = project_path / "package.json"
    if package_json.exists():
        return _read_json(package_json)
    return {}


def _project_kind(project_id: str, project_path: Path, meta: dict) -> str:
    package = _package_manifest(project_path)
    deps = {**(package.get("dependencies") or {}), **(package.get("devDependencies") or {})}
    scripts = package.get("scripts") or {}

    if project_id == "growth-dashboard" or ("wrangler" in deps and "deploy" in scripts):
        return "cloudflare_pages"
    if (
        _has_any(project_path, "next.config.js", "next.config.ts", "next.config.mjs")
        or "next" in deps
        or any("next " in str(command) for command in scripts.values())
    ):
        return "next_frontend"
    if "@modelcontextprotocol/sdk" in deps:
        return "mcp_service"
    if meta.get("type") == "php":
        return "php_app"
    if meta.get("type") == "html":
        return "static_site"
    if _has_any(project_path, "pyproject.toml", "requirements.txt"):
        return "python_service"
    return "generic"


def _generic_actions(project_id: str, project_name: str, kind: str) -> list[dict]:
    if kind == "cloudflare_pages":
        return [
            _action(
                f"{project_id}-build-static",
                "Rebuild static export",
                "Validate the public export and Cloudflare Pages-ready output before deployment.",
                f"Review the {project_name} repo, verify the Cloudflare Pages export is current, run the build, and report any deployment blockers.",
            ),
        ]
    if kind == "next_frontend":
        return [
            _action(
                f"{project_id}-frontend-verify",
                "Validate frontend readiness",
                "Check env files, build output, and the app shell before release or local handoff.",
                f"Review the {project_name} frontend, verify required environment setup, run a production build, and summarize any launch blockers.",
            ),
        ]
    if kind == "mcp_service":
        return [
            _action(
                f"{project_id}-mcp-verify",
                "Validate MCP service",
                "Confirm the build output, runtime entrypoint, and provider configuration for the MCP server.",
                f"Review the {project_name} MCP service, verify its build and runtime entrypoint, and summarize the next steps to run it safely.",
            ),
        ]
    if kind == "python_service":
        return [
            _action(
                f"{project_id}-service-verify",
                "Validate backend stack",
                "Check infra prerequisites, env/config coverage, and service start commands for the Python backend.",
                f"Review the {project_name} backend, verify infrastructure dependencies and startup commands, and outline the safest path to get it running.",
            ),
        ]
    if kind == "php_app":
        return [
            _action(
                f"{project_id}-deploy-audit",
                "Audit deploy readiness",
                "Confirm the PHP app has its deploy files, schema migration, and cron setup documented and ready.",
                f"Review the {project_name} PHP project, verify deploy files and cron prerequisites, and summarize the safest deployment checklist.",
            ),
        ]
    if kind == "static_site":
        return [
            _action(
                f"{project_id}-content-smoke",
                "Smoke-check static site",
                "Review core pages, menu/order links, and static SEO assets before publishing changes.",
                f"Review the {project_name} static website, validate its critical pages and ordering paths, and report the highest priority fixes or publish steps.",
            ),
        ]
    return []


def _qa_simulation_action(project_id: str, project_name: str, kind: str) -> dict:
    kind_label = kind.replace("_", " ") if kind else "project"
    return _action(
        f"{project_id}-qa-simulate",
        "Run 1k tester simulation",
        "Simulate the CEO-to-department-to-tester loop with 1,000 testers and up to 100 feedback rounds.",
        f"Run a QA simulation for {project_name} as a {kind_label}, validate UI, workflow, feature coverage, and defect readiness, and stop only when the tester score reaches at least 8.5/10.",
        action_label="Run simulation",
        action_type="qa_simulation",
    )


def _qa_live_action(project_id: str, project_name: str, kind: str) -> dict:
    kind_label = kind.replace("_", " ") if kind else "project"
    return _action(
        f"{project_id}-qa-live",
        "Run live browser QA",
        "Open the real app in a browser, test desktop/tablet/mobile, and auto-start the fix -> retest loop if the score is too low.",
        f"Run live browser QA for {project_name} as a {kind_label}, validate UI, workflow, and feature behavior in a real browser, then create remediation tasks if the score stays below 8.5/10.",
        action_label="Run live QA",
        action_type="qa_live",
    )


def build_project_ops_profile(project_id: str, project_path: Path, meta: dict, status: str) -> dict:
    package = _package_manifest(project_path)
    scripts = package.get("scripts") or {}
    kind = _project_kind(project_id, project_path, meta)
    signals: list[dict] = []
    suggestions: list[dict] = []

    if status == "running":
        signals.append(_signal("Runtime", "Service responding", "ok"))
    elif status == "idle":
        signals.append(_signal("Runtime", "Source present but not responding", "warning"))
    else:
        signals.append(_signal("Runtime", "Project not detected or offline", "error"))

    if kind in {"cloudflare_pages", "next_frontend", "mcp_service"}:
        signals.append(_signal("package.json", "present" if package else "missing", "ok" if package else "error"))
        if scripts:
            summary = ", ".join(sorted(scripts.keys())[:4])
            signals.append(_signal("Scripts", summary or "none", "ok" if summary else "warning"))
        if kind == "cloudflare_pages":
            public_dir = project_path / "public"
            signals.append(_signal("Static export", "public/ ready" if public_dir.exists() else "public/ missing", "ok" if public_dir.exists() else "warning"))
            suggestions.extend(_generic_actions(project_id, meta["name"], kind))
        elif kind == "next_frontend":
            env_example = _has_any(project_path, ".env.local.example", ".env.example")
            signals.append(_signal("Env template", "present" if env_example else "missing", "ok" if env_example else "warning"))
            build_dir = project_path / ".next"
            signals.append(_signal("Build cache", ".next present" if build_dir.exists() else ".next missing", "ok" if build_dir.exists() else "warning"))
            suggestions.extend(_generic_actions(project_id, meta["name"], kind))
        elif kind == "mcp_service":
            dist_dir = project_path / "dist"
            signals.append(_signal("Build output", "dist present" if dist_dir.exists() else "dist missing", "ok" if dist_dir.exists() else "warning"))
            suggestions.extend(_generic_actions(project_id, meta["name"], kind))

    elif kind == "python_service":
        pyproject = project_path / "pyproject.toml"
        requirements = project_path / "requirements.txt"
        signals.append(_signal("Python config", "pyproject.toml" if pyproject.exists() else "requirements.txt" if requirements.exists() else "missing", "ok" if pyproject.exists() or requirements.exists() else "error"))
        docker_compose = _has_any(project_path, "docker-compose.yml", "docker-compose.yaml")
        if docker_compose:
            signals.append(_signal("Infrastructure", "docker-compose present", "ok"))
        env_example = _has_any(project_path, ".env.example", ".env.local.example")
        signals.append(_signal("Env template", "present" if env_example else "missing", "ok" if env_example else "warning"))
        if project_id == "review-system":
            signals.append(_signal("Worker stack", "Redis/RQ workflow detected", "ok"))
        suggestions.extend(_generic_actions(project_id, meta["name"], kind))

    elif kind == "php_app":
        cron_file = _has_any(project_path, "cron.php")
        sql_dir = _has_any(project_path, "sql", "sql/schema_v2.sql")
        signals.append(_signal("Cron entry", "cron.php present" if cron_file else "cron missing", "ok" if cron_file else "warning"))
        signals.append(_signal("Schema assets", "sql assets present" if sql_dir else "sql assets missing", "ok" if sql_dir else "warning"))
        suggestions.extend(_generic_actions(project_id, meta["name"], kind))

    elif kind == "static_site":
        index_file = project_path / "index.html"
        sitemap_file = project_path / "sitemap.xml"
        signals.append(_signal("Entry page", "index.html present" if index_file.exists() else "index.html missing", "ok" if index_file.exists() else "error"))
        signals.append(_signal("SEO asset", "sitemap.xml present" if sitemap_file.exists() else "sitemap.xml missing", "ok" if sitemap_file.exists() else "warning"))
        suggestions.extend(_generic_actions(project_id, meta["name"], kind))

    else:
        suggestions.extend(_generic_actions(project_id, meta["name"], kind))

    if kind in {"cloudflare_pages", "next_frontend", "php_app", "static_site"}:
        suggestions.append(_qa_live_action(project_id, meta["name"], kind))

    suggestions.append(_qa_simulation_action(project_id, meta["name"], kind))

    return {
        "kind": kind,
        "signals": signals[:6],
        "suggestions": suggestions[:4],
    }
