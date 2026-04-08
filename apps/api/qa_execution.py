from __future__ import annotations

import time
from typing import Any


_WEIGHTS = {
    "errors": 0.35,
    "ui": 0.20,
    "workflow": 0.20,
    "features": 0.25,
}

_PROFILES = [
    {"name": "desktop", "viewport": {"width": 1440, "height": 900}},
    {"name": "tablet", "viewport": {"width": 1024, "height": 768}},
    {"name": "mobile", "viewport": {"width": 390, "height": 844}},
]


def _clamp(value: float, minimum: float, maximum: float) -> float:
    return max(minimum, min(maximum, value))


def _normalize_url(project: dict[str, Any]) -> str | None:
    url = (project.get("url") or "").strip()
    if url:
        if url.startswith(("http://", "https://")):
            return url
        if "." in url:
            return f"https://{url}"
        return f"http://{url}"

    port = project.get("port")
    if port and project.get("status") in {"online", "running", "idle"}:
        return f"http://127.0.0.1:{port}"
    return None


def _score_profile(profile: dict[str, Any]) -> dict[str, Any]:
    status_code = profile.get("status_code")
    console_error_count = len(profile.get("console_errors") or [])
    page_error_count = len(profile.get("page_errors") or [])
    load_ms = float(profile.get("load_ms") or 0.0)
    dom = profile.get("dom") or {}

    text_length = int(dom.get("text_length") or 0)
    headings = int(dom.get("headings") or 0)
    inputs = int(dom.get("inputs") or 0)
    buttons = int(dom.get("buttons") or 0)
    links = int(dom.get("links") or 0)
    main_landmarks = int(dom.get("main_landmarks") or 0)

    error_penalty = (console_error_count * 0.45) + (page_error_count * 0.65)
    status_penalty = 1.5 if (status_code or 0) >= 500 else 0.8 if (status_code or 0) >= 400 else 0.0
    load_penalty = 0.6 if load_ms > 7000 else 0.3 if load_ms > 3500 else 0.0

    errors_score = _clamp(9.45 - error_penalty - status_penalty - load_penalty, 3.8, 9.5)
    ui_score = _clamp(
        8.35
        + (0.25 if headings >= 1 else -0.55)
        + (0.2 if main_landmarks >= 1 else -0.35)
        + (0.15 if text_length >= 250 else -0.55)
        - (0.15 if buttons + links == 0 else 0.0)
        - (console_error_count * 0.1),
        4.5,
        9.4,
    )
    workflow_score = _clamp(
        8.1
        + (0.2 if links + buttons >= 3 else -0.45)
        + (0.15 if inputs >= 1 else 0.0)
        - (0.22 if load_ms > 5000 else 0.0)
        - (page_error_count * 0.18),
        4.5,
        9.3,
    )
    features_score = _clamp(
        8.0
        + (0.15 if text_length >= 150 else -0.5)
        + (0.12 if headings >= 1 else -0.2)
        + (0.12 if buttons + links + inputs >= 4 else -0.35)
        - (0.12 if (status_code or 200) >= 400 else 0.0),
        4.4,
        9.25,
    )

    findings: list[dict[str, Any]] = []
    if (status_code or 0) >= 400:
        findings.append(
            {
                "category": "errors",
                "severity": "high",
                "title": f"{profile['name'].title()} viewport returned HTTP {status_code}",
                "detail": "The page did not load successfully for this viewport.",
            }
        )
    if console_error_count or page_error_count:
        findings.append(
            {
                "category": "errors",
                "severity": "high" if console_error_count + page_error_count >= 2 else "medium",
                "title": f"{profile['name'].title()} viewport produced browser errors",
                "detail": f"{console_error_count} console error(s) and {page_error_count} page error(s) were captured.",
            }
        )
    if headings == 0 or main_landmarks == 0:
        findings.append(
            {
                "category": "ui",
                "severity": "medium",
                "title": f"{profile['name'].title()} viewport lacks structure cues",
                "detail": "The page is missing a heading or main landmark, which weakens UI clarity and accessibility.",
            }
        )
    if links + buttons == 0:
        findings.append(
            {
                "category": "workflow",
                "severity": "medium",
                "title": f"{profile['name'].title()} viewport has no obvious actions",
                "detail": "No links or buttons were detected, so the main workflow could not be exercised confidently.",
            }
        )
    if text_length < 120:
        findings.append(
            {
                "category": "features",
                "severity": "medium",
                "title": f"{profile['name'].title()} viewport appears content-thin",
                "detail": "The rendered page content looks sparse, which often signals partial hydration or broken content blocks.",
            }
        )

    overall = round(
        (errors_score * _WEIGHTS["errors"])
        + (ui_score * _WEIGHTS["ui"])
        + (workflow_score * _WEIGHTS["workflow"])
        + (features_score * _WEIGHTS["features"]),
        2,
    )
    return {
        "scores": {
            "errors": round(errors_score, 2),
            "ui": round(ui_score, 2),
            "workflow": round(workflow_score, 2),
            "features": round(features_score, 2),
        },
        "final_score": overall,
        "findings": findings,
    }


def _run_profile(context: Any, target_url: str, profile: dict[str, Any], timeout_ms: int) -> dict[str, Any]:
    page = context.new_page()
    console_errors: list[str] = []
    page_errors: list[str] = []
    page.on("console", lambda message: console_errors.append(message.text) if message.type == "error" else None)
    page.on("pageerror", lambda error: page_errors.append(str(error)))

    response = None
    start = time.perf_counter()
    try:
        response = page.goto(target_url, wait_until="domcontentloaded", timeout=timeout_ms)
        try:
            page.wait_for_load_state("networkidle", timeout=min(timeout_ms, 5000))
        except Exception:
            pass
        dom = page.evaluate(
            """() => ({
                text_length: document.body?.innerText?.trim().length ?? 0,
                headings: document.querySelectorAll('h1, h2, h3').length,
                links: document.querySelectorAll('a').length,
                buttons: document.querySelectorAll('button').length,
                inputs: document.querySelectorAll('input, select, textarea').length,
                forms: document.querySelectorAll('form').length,
                images: document.querySelectorAll('img').length,
                main_landmarks: document.querySelectorAll('main, [role="main"]').length,
            })"""
        )
        payload = {
            "name": profile["name"],
            "url": page.url,
            "title": page.title(),
            "status_code": response.status if response else None,
            "load_ms": round((time.perf_counter() - start) * 1000, 2),
            "console_errors": console_errors[:8],
            "page_errors": page_errors[:8],
            "dom": dom,
        }
    finally:
        page.close()

    scored = _score_profile(payload)
    payload.update(scored)
    return payload


def _fallback_failure(project: dict[str, Any], target_url: str | None, reason: str) -> dict[str, Any]:
    findings = [
        {
            "category": "errors",
            "severity": "high",
            "title": "Live browser QA could not start",
            "detail": reason,
        }
    ]
    return {
        "project_id": project.get("id"),
        "project_name": project.get("name"),
        "target_url": target_url,
        "profiles": [],
        "aggregate_scores": {"errors": 3.8, "ui": 5.0, "workflow": 5.0, "features": 5.0},
        "final_score": 4.53,
        "pass_threshold": None,
        "passed": False,
        "summary": reason,
        "findings": findings,
    }


def run_live_project_qa(
    project: dict[str, Any],
    *,
    pass_threshold: float = 8.5,
    timeout_ms: int = 15000,
) -> dict[str, Any]:
    pass_threshold = float(_clamp(pass_threshold, 6.0, 9.8))
    timeout_ms = int(_clamp(float(timeout_ms), 4000, 60000))
    target_url = _normalize_url(project)
    if not target_url:
        result = _fallback_failure(project, target_url, "No live URL or reachable local port is configured for this project.")
        result["pass_threshold"] = pass_threshold
        return result

    try:
        from playwright.sync_api import sync_playwright
    except Exception:
        result = _fallback_failure(project, target_url, "Playwright is not installed, so live browser QA cannot launch yet.")
        result["pass_threshold"] = pass_threshold
        return result

    profiles: list[dict[str, Any]] = []
    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            try:
                for profile in _PROFILES:
                    context = browser.new_context(viewport=profile["viewport"], ignore_https_errors=True)
                    try:
                        profiles.append(_run_profile(context, target_url, profile, timeout_ms))
                    finally:
                        context.close()
            finally:
                browser.close()
    except Exception as exc:
        result = _fallback_failure(project, target_url, f"Live browser QA crashed before finishing: {exc}")
        result["pass_threshold"] = pass_threshold
        return result

    aggregate_scores = {
        key: round(sum(profile["scores"][key] for profile in profiles) / max(len(profiles), 1), 2)
        for key in _WEIGHTS
    }
    final_score = round(sum(aggregate_scores[key] * _WEIGHTS[key] for key in _WEIGHTS), 2)

    findings: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for profile in profiles:
        for finding in profile.get("findings") or []:
            marker = (finding["title"], finding["detail"])
            if marker in seen:
                continue
            seen.add(marker)
            findings.append(finding)

    findings.sort(key=lambda item: (item["severity"] != "high", item["category"], item["title"]))
    if not findings and final_score < pass_threshold:
        findings.append(
            {
                "category": "workflow",
                "severity": "medium",
                "title": "Live browser QA stayed below the release threshold",
                "detail": "The page loaded, but the combined UI, workflow, and feature signals still need another fix cycle.",
            }
        )

    return {
        "project_id": project.get("id"),
        "project_name": project.get("name"),
        "target_url": target_url,
        "profiles": profiles,
        "aggregate_scores": aggregate_scores,
        "final_score": final_score,
        "pass_threshold": pass_threshold,
        "passed": final_score >= pass_threshold,
        "summary": (
            f"Live browser QA ran across {len(profiles)} viewport(s) and finished at {final_score:.2f}/10."
            if profiles
            else "Live browser QA did not finish."
        ),
        "findings": findings[:8],
    }
