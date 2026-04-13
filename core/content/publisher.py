"""
Content Publisher — writes validated HTML to project repo and pushes via git.
Only runs AFTER human approval from the dashboard.
"""

from __future__ import annotations

import logging
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Any

logger = logging.getLogger("content.publisher")


class ContentPublisher:
    """Writes blog posts to project repos and pushes via git."""

    def publish(self, project_id: str, slug: str, html: str, topic: dict | None = None) -> dict:
        """Write HTML file, update blog index, git commit + push.

        Returns:
            {"published": True, "filename": "blog-xxx.html", "git_commit": "abc123", ...}
        """
        from core.agents.dev_agent import MASTER_DIR, PROJECT_FOLDERS

        folder = PROJECT_FOLDERS.get(project_id, project_id)
        project_path = MASTER_DIR / folder

        if not project_path.exists():
            return {"published": False, "error": f"Project path not found: {project_path}"}

        filename = f"blog-{slug}.html"
        filepath = project_path / filename

        try:
            # 1. Write HTML file
            filepath.write_text(html, encoding="utf-8")
            logger.info("Wrote %s (%d bytes)", filepath, len(html))

            # 2. Update blog index (if exists)
            self._update_blog_index(project_path, filename, topic or {})

            # 3. Git add + commit + push
            git_result = self._git_publish(project_path, filename, topic or {})

            # 4. Verify file exists
            if not filepath.exists():
                return {"published": False, "error": "File not found after write"}

            return {
                "published": True,
                "filename": filename,
                "filepath": str(filepath),
                "word_count": len(html.split()),
                "published_at": datetime.now().isoformat(),
                **git_result,
            }

        except Exception as exc:
            logger.exception("Publishing failed: %s", exc)
            # Try to rollback
            self._rollback(project_path)
            return {"published": False, "error": str(exc)}

    def _git_run(self, project_path: Path, *args: str) -> str:
        """Run a git command."""
        try:
            result = subprocess.run(
                ["git"] + list(args),
                cwd=str(project_path),
                capture_output=True, text=True, timeout=30,
            )
            return result.stdout.strip() if result.returncode == 0 else f"[error] {result.stderr.strip()}"
        except Exception as e:
            return f"[error] {e}"

    def _git_publish(self, project_path: Path, filename: str, topic: dict) -> dict:
        """Git add, commit, push."""
        title = topic.get("title", filename)
        date = datetime.now().strftime("%Y-%m-%d")

        # Stage files
        self._git_run(project_path, "add", filename)
        # Also stage blog.html if it was updated
        blog_index = project_path / "blog.html"
        if blog_index.exists():
            self._git_run(project_path, "add", "blog.html")

        # Commit
        commit_msg = f"blog: {title} [{date}]"
        commit_result = self._git_run(project_path, "commit", "-m", commit_msg)

        # Get commit hash
        commit_hash = self._git_run(project_path, "rev-parse", "--short", "HEAD")

        # Push
        push_result = self._git_run(project_path, "push", "origin", "main")
        if "[error]" in push_result:
            # Try pushing to master instead
            push_result = self._git_run(project_path, "push", "origin", "master")

        return {
            "git_commit": commit_hash,
            "git_commit_message": commit_msg,
            "git_push": push_result,
        }

    def _update_blog_index(self, project_path: Path, filename: str, topic: dict) -> None:
        """Add new post card to blog.html if it exists."""
        blog_html_path = project_path / "blog.html"
        if not blog_html_path.exists():
            return

        try:
            content = blog_html_path.read_text(encoding="utf-8")

            # Create a new blog card
            title = topic.get("title", filename.replace("blog-", "").replace(".html", "").replace("-", " ").title())
            tag = topic.get("section_tag", "Blog")
            description = topic.get("meta_description", "")[:120]

            card_html = (
                f'\n            <a href="{filename}" class="blog-card">\n'
                f'                <div class="blog-card-content">\n'
                f'                    <div class="section-tag">{tag}</div>\n'
                f'                    <h3>{title}</h3>\n'
                f'                    <p>{description}</p>\n'
                f'                </div>\n'
                f'            </a>'
            )

            # Find the blog grid and prepend
            grid_markers = ["blog-grid", "blog-cards", "blog-list"]
            for marker in grid_markers:
                idx = content.find(f'class="{marker}"')
                if idx > 0:
                    # Find the closing > of the container div
                    close = content.find(">", idx)
                    if close > 0:
                        content = content[:close + 1] + card_html + content[close + 1:]
                        blog_html_path.write_text(content, encoding="utf-8")
                        logger.info("Updated blog index: added card for %s", filename)
                        return

            logger.warning("Could not find blog grid in blog.html — skipping index update")
        except Exception as exc:
            logger.warning("Failed to update blog index: %s", exc)

    def _rollback(self, project_path: Path) -> None:
        """Attempt to undo the last commit if push failed."""
        try:
            self._git_run(project_path, "reset", "HEAD~1")
            logger.info("Rolled back last commit")
        except Exception:
            pass
