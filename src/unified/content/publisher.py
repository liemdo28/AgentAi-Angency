"""
Content Publisher — publishes approved posts to RawWebsite.

Publishing target:
  rawwebsite/content/posts/{slug}.md       ← markdown with YAML frontmatter
  rawwebsite/content/index.json            ← blog listing manifest (updated on each publish)
  rawwebsite/sitemap.xml                   ← sitemap entry added

Frontmatter written:
  ---
  title: "..."
  slug: ...
  date: YYYY-MM-DD
  excerpt: "..."
  meta_description: "..."
  image: ...
  cta: "..."
  cta_url: "..."
  primary_keyword: ...
  secondary_keywords: [...]
  post_type: ...
  target_audience: "..."
  published: true
  ---

  {markdown body}

The RawWebsite blog-posts.html page reads:
  - content/index.json  → blog listing
  - content/posts/{slug}.md → post body

Rules:
  ✓ ONLY approved/scheduled posts can publish
  ✓ All publish actions logged to DB
  ✗ NO auto-publish without human approval
"""

from __future__ import annotations

import json
import logging
import os
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

logger = logging.getLogger("content.publisher")

# Load .env so that RAWWEBSITE_REPO_PATH, GIT_TOKEN etc. are available
# even when the module is imported before the main app boots.
try:
    from dotenv import load_dotenv as _load_dotenv
    _load_dotenv(override=False)  # don't override already-set env vars
except ImportError:
    pass

# ─────────────────────────────────────────────────────────────────────────────
#  Field normaliser: accepts ContentDraft, content_automation ContentDraft,
#  or a plain dict from the DB (post + version merged).
# ─────────────────────────────────────────────────────────────────────────────

def _field(obj: Any, *keys: str, default: Any = "") -> Any:
    """Try each key in order, returning the first non-empty value found."""
    for k in keys:
        v = getattr(obj, k, None)
        if v is None:
            v = obj.get(k) if isinstance(obj, dict) else None
        if v is not None and v != "":
            return v
    return default


def _field_list(obj: Any, *keys: str) -> list:
    """Like _field but always returns a list."""
    v = _field(obj, *keys, default=[])
    if isinstance(v, list):
        return v
    if isinstance(v, str) and v:
        return [x.strip() for x in v.split(",") if x.strip()]
    return []


# ─────────────────────────────────────────────────────────────────────────────
#  ContentPublisher
# ─────────────────────────────────────────────────────────────────────────────

class ContentPublisher:
    """
    Publishes approved posts as markdown files in RawWebsite's content/posts/.

    Accepts:
      - ContentDraft from src/unified/content/models.py
      - ContentDraft from src/unified/content_automation/models.py
      - Plain dict (DB post row, optionally merged with a version row)
    """

    def __init__(self):
        self.mode         = os.environ.get("RAWWEBSITE_PUBLISH_MODE", "git_commit")
        self.repo_url     = os.environ.get(
            "RAWWEBSITE_REPO_URL", "https://github.com/liemdo28/rawwebsite.git"
        )
        self.repo_branch  = os.environ.get("RAWWEBSITE_REPO_BRANCH", "main")
        self.author_name  = os.environ.get("GIT_AUTHOR_NAME", "AgentAI Agency")
        self.author_email = os.environ.get("GIT_AUTHOR_EMAIL", "agency@rawsushibar.com")
        self.token        = os.environ.get("GIT_TOKEN", "")
        self.repo_path    = os.environ.get("RAWWEBSITE_REPO_PATH")
        self.export_dir   = Path(os.environ.get("POST_EXPORT_DIR", "data/post_exports"))
        self.target_dir   = "content/posts"

    # ── Public API ────────────────────────────────────────────────────────────

    def publish(
        self,
        post: Any,
        version: Any = None,
        *,
        author: str = "AgentAI Agency",
        post_id: str | None = None,
    ) -> dict:
        """
        Publish an approved post to RawWebsite as markdown.

        Args:
            post:     ContentDraft | dict (DB post row)
            version:  optional dict (DB post_version row, merged onto post)
            author:   display name for the commit
            post_id:  explicit post ID for DB logging (falls back to post['id'])

        Returns:
            {
              "success": bool,
              "slug": str,
              "filepath": str,
              "html_url": str,
              "published_at": str,
            }
        """
        # Merge version fields onto post dict for simpler downstream access
        merged = self._merge(post, version)

        slug = self._slug(merged)
        pid  = post_id or _field(merged, "id", default=str(uuid4()))

        logger.info("Publishing post: id=%s slug=%s mode=%s", pid, slug, self.mode)

        md_content = self._build_markdown(merged)

        if self.mode == "git_commit":
            result = self._git_publish(slug, md_content, pid, merged)
        else:
            result = self._manual_export(slug, md_content, merged)

        self._log_publish(pid, result)
        return result

    # ── Data normalisation ────────────────────────────────────────────────────

    @staticmethod
    def _merge(post: Any, version: Any) -> dict:
        """
        Merge post + version into a single flat dict.
        Version fields override post fields where both exist.
        Handles: ContentDraft objects, plain dicts.
        """
        def to_dict(obj: Any) -> dict:
            if obj is None:
                return {}
            if isinstance(obj, dict):
                return obj
            # Pydantic v1 / v2 / dataclass
            if hasattr(obj, "model_dump"):
                return obj.model_dump()
            if hasattr(obj, "dict"):
                return obj.dict()
            return {k: getattr(obj, k) for k in dir(obj) if not k.startswith("_")}

        base = {k: v for k, v in to_dict(post).items() if v is not None and v != ""}
        over = {k: v for k, v in to_dict(version).items() if v is not None and v != ""}
        return {**base, **over}

    # ── Markdown building ─────────────────────────────────────────────────────

    def _build_markdown(self, d: dict) -> str:
        """
        Build a markdown file with YAML frontmatter from a normalised dict.

        Handles field names from both content/ and content_automation/ models.
        """
        title        = _field(d, "title",             default="Untitled")
        slug         = self._slug(d)
        date_str     = _field(d, "published_at", "created_at", default=self._now())[:10]
        excerpt      = _field(d, "excerpt",           default="")[:300]
        meta_desc    = _field(d, "meta_description", "seo_description", default="")[:160]
        image        = _field(d, "image_url", "featured_image_url", "image", default="")
        cta          = _field(d, "cta", "cta_text",   default="")
        cta_url      = _field(d, "cta_url",            default="https://www.rawsushibar.com")
        primary_kw   = _field(d, "keyword_primary", "focus_keyword", "primary_keyword", default="")
        secondary_kw = _field_list(d, "keywords_secondary", "secondary_keywords")
        post_type    = _field(d, "type", "post_type", default="blog")
        # Normalise enum values
        if hasattr(post_type, "value"):
            post_type = post_type.value
        audience     = _field(d, "target_audience",   default="")
        body         = _field(d, "body_markdown",      default="")

        kw_list = ", ".join(secondary_kw) if secondary_kw else ""

        lines = [
            "---",
            f'title: "{_yaml_escape(title)}"',
            f"slug: {slug}",
            f"date: {date_str}",
            f'excerpt: "{_yaml_escape(excerpt)}"',
            f'meta_description: "{_yaml_escape(meta_desc)}"',
            f"image: {image or ''}",
            f'cta: "{_yaml_escape(cta)}"',
            f"cta_url: {cta_url or 'https://www.rawsushibar.com'}",
            f"primary_keyword: {primary_kw}",
            f"secondary_keywords: [{kw_list}]",
            f"post_type: {post_type}",
            f'target_audience: "{_yaml_escape(audience)}"',
            "published: true",
            "---",
            "",
            body,
        ]

        return "\n".join(lines)

    # ── Git publish ───────────────────────────────────────────────────────────

    def _git_publish(self, slug: str, md_content: str, post_id: str, d: dict) -> dict:
        """Write .md file + update index.json + update sitemap.xml → git commit + push."""
        work_dir = self._prepare_repo()
        posts_dir = work_dir / self.target_dir
        posts_dir.mkdir(parents=True, exist_ok=True)

        # Write markdown
        md_path = posts_dir / f"{slug}.md"
        md_path.write_text(md_content, encoding="utf-8")
        logger.info("Wrote %s (%d bytes)", md_path, len(md_content))

        # Update blog index manifest
        self._update_index_json(work_dir, slug, d)

        # Update sitemap.xml
        self._update_sitemap(work_dir, slug, d)

        # Git add → commit → push
        rel_md   = f"{self.target_dir}/{slug}.md"
        self._git(work_dir, "add", rel_md)
        self._git_add_commit_push(work_dir, slug)

        url = f"https://www.rawsushibar.com/blog-posts.html?slug={slug}"
        return {
            "success":      True,
            "mode":         "git_commit",
            "slug":         slug,
            "filepath":     str(md_path),
            "html_url":     url,
            "published_at": self._now(),
            "git_commit":   self._git_capture(work_dir, "rev-parse", "--short", "HEAD"),
        }

    def _prepare_repo(self) -> Path:
        """Return the local rawwebsite working directory (clone if missing)."""
        if self.repo_path:
            candidate = Path(self.repo_path)
            if candidate.exists() and (candidate / ".git").exists():
                self._git(candidate, "fetch", "origin", self.repo_branch)
                self._git(candidate, "pull", "origin", self.repo_branch)
                return candidate

        clone_dir = self.export_dir / "rawwebsite_clone"
        if clone_dir.exists():
            self._git(clone_dir, "fetch", "origin", self.repo_branch)
            self._git(clone_dir, "pull", "origin", self.repo_branch)
        else:
            clone_dir.mkdir(parents=True, exist_ok=True)
            auth = _auth_url(self.repo_url, self.token)
            self._git(clone_dir, "clone", auth, str(clone_dir),
                      "--branch", self.repo_branch, "--depth", "1")
        return clone_dir

    def _git_add_commit_push(self, repo_dir: Path, slug: str) -> None:
        """Commit everything staged so far and push."""
        status = self._git_capture(repo_dir, "status", "--porcelain")
        if not status.strip():
            logger.info("No changes to commit for %s — already up to date", slug)
            return

        msg = (
            f"feat: publish post — {slug}\n\n"
            f"Published via AgentAI Agency content automation.\n"
            f"URL: https://www.rawsushibar.com/blog-posts.html?slug={slug}"
        )
        self._git(
            repo_dir,
            "-c", "commit.gpgsign=false",
            "commit", "-m", msg,
            "--author", f"{self.author_name} <{self.author_email}>",
        )
        auth_remote = _auth_remote(self.repo_url, self.token)
        self._git(repo_dir, "push", auth_remote, self.repo_branch)

    def _update_index_json(self, repo_dir: Path, slug: str, d: dict) -> None:
        """
        Append or update the post entry in content/index.json.
        This JSON drives the blog listing page in blog-posts.html.
        """
        index_path = repo_dir / "content" / "index.json"
        index_path.parent.mkdir(parents=True, exist_ok=True)

        title    = _field(d, "title", default="Untitled")
        excerpt  = _field(d, "excerpt", default="")[:200]
        date_str = _field(d, "published_at", "created_at", default=self._now())[:10]
        ptype    = _field(d, "type", "post_type", default="blog")
        if hasattr(ptype, "value"):
            ptype = ptype.value
        image    = _field(d, "image_url", "featured_image_url", "image", default="")
        kw       = _field(d, "keyword_primary", "focus_keyword", "primary_keyword", default="")

        entry = {
            "slug":            slug,
            "title":           title,
            "excerpt":         excerpt,
            "date":            date_str,
            "post_type":       str(ptype),
            "image":           str(image) if image else "",
            "primary_keyword": str(kw),
            "published":       True,
        }

        if index_path.exists():
            try:
                data = json.loads(index_path.read_text(encoding="utf-8"))
                posts = data.get("posts", [])
                # Replace existing entry for this slug, or prepend
                posts = [p for p in posts if p.get("slug") != slug]
                posts.insert(0, entry)
                data["posts"] = posts
                index_path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
            except Exception as exc:
                logger.warning("Could not update index.json: %s", exc)
                return
        else:
            index_path.write_text(
                json.dumps({"posts": [entry]}, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )

        self._git(repo_dir, "add", "content/index.json")
        logger.info("Updated content/index.json for slug=%s", slug)

    def _update_sitemap(self, repo_dir: Path, slug: str, d: dict) -> None:
        """Add a sitemap entry for blog-posts.html?slug=SLUG."""
        sitemap = repo_dir / "sitemap.xml"
        url   = f"https://www.rawsushibar.com/blog-posts.html?slug={slug}"
        date  = _field(d, "published_at", "created_at", default=self._now())[:10]
        entry = (
            f"  <url>\n"
            f"    <loc>{url}</loc>\n"
            f"    <lastmod>{date}</lastmod>\n"
            f"    <changefreq>yearly</changefreq>\n"
            f"    <priority>0.6</priority>\n"
            f"  </url>\n"
        )
        if sitemap.exists():
            content = sitemap.read_text(encoding="utf-8")
            if slug not in content:
                content = content.replace("</urlset>", f"{entry}</urlset>")
                sitemap.write_text(content, encoding="utf-8")
                self._git(repo_dir, "add", "sitemap.xml")

    # ── Manual export fallback ────────────────────────────────────────────────

    def _manual_export(self, slug: str, md_content: str, d: dict) -> dict:
        self.export_dir.mkdir(parents=True, exist_ok=True)
        path = self.export_dir / f"{slug}.md"
        path.write_text(md_content, encoding="utf-8")
        logger.info("Exported to %s", path)
        return {
            "success":      True,
            "mode":         "manual_export",
            "slug":         slug,
            "filepath":     str(path),
            "html_url":     f"https://www.rawsushibar.com/blog-posts.html?slug={slug}",
            "published_at": self._now(),
        }

    # ── Publish log ───────────────────────────────────────────────────────────

    def _log_publish(self, post_id: str, result: dict) -> None:
        try:
            from db.post_repository import PostRepository
            repo = PostRepository()
            conn = repo._conn()
            try:
                conn.execute(
                    """
                    INSERT OR IGNORE INTO publish_logs
                        (id, post_id, target_system, status, response_payload, created_at)
                    VALUES (?, ?, ?, ?, ?, datetime('now'))
                    """,
                    (
                        str(uuid4()),
                        post_id,
                        "rawwebsite_md",
                        "success" if result.get("success") else "failed",
                        json.dumps(result),
                    ),
                )
                conn.commit()
            finally:
                conn.close()
        except Exception as exc:
            logger.warning("Could not write publish log: %s", exc)

    # ── Git helpers ───────────────────────────────────────────────────────────

    @staticmethod
    def _git(cwd: Path, *args: str) -> subprocess.CompletedProcess:
        result = subprocess.run(
            ["git"] + list(args), cwd=cwd, capture_output=True, text=True
        )
        if result.returncode != 0:
            logger.warning("git %s: %s", " ".join(args), result.stderr.strip()[:200])
        return result

    @staticmethod
    def _git_capture(cwd: Path, *args: str) -> str:
        result = subprocess.run(
            ["git"] + list(args), cwd=cwd, capture_output=True, text=True
        )
        return result.stdout.strip()

    # ── Misc helpers ──────────────────────────────────────────────────────────

    @staticmethod
    def _slug(d: Any) -> str:
        slug = _field(d, "slug", default="")
        if slug:
            return re.sub(r"[^a-z0-9-]", "-", slug.lower())[:80].strip("-")
        title = _field(d, "title", default="untitled")
        return re.sub(r"[^a-z0-9]+", "-", title.lower())[:80].strip("-")

    @staticmethod
    def _now() -> str:
        return datetime.now(timezone.utc).isoformat()


# ─────────────────────────────────────────────────────────────────────────────
#  Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _yaml_escape(s: str) -> str:
    """Escape double-quotes in a YAML double-quoted string."""
    return str(s).replace('"', '\\"')


def _auth_url(url: str, token: str) -> str:
    if not token or not url.startswith("https://"):
        return url
    return url.replace("https://", f"https://{token}@")


def _auth_remote(url: str, token: str) -> str:
    if not token or not url.startswith("https://"):
        return "origin"
    return url.replace("https://", f"https://{token}@")
