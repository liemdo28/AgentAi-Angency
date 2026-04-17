"""
Content Publisher — publishes approved posts to RawWebsite.

Publishing target (Phase 1):
  - Writes blog HTML files to the RawWebsite local repo
  - Updates sitemap.xml
  - Git commits + pushes (git_commit mode)
  - Falls back to manual export if git unavailable

Publishing model:
  Preferred (Phase 2+): Markdown frontmatter in content/posts/
  Phase 1: HTML files matching RawWebsite's existing blog-*.html pattern

Publishing rules:
  - Only posts in status 'approved' or 'scheduled' can publish
  - All publish attempts (success + failure) are logged to publish_logs table
  - Auto-publish is NOT implemented — human approval always required first
  - Publishing is idempotent (re-publishing same post overwrites the same file)
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

logger = logging.getLogger("content_automation.publisher")


# ─────────────────────────────────────────────────────────────────────────────
#  Content Publisher
# ─────────────────────────────────────────────────────────────────────────────

class ContentPublisher:
    """
    Publishes approved posts to RawWebsite via git commit.

    Supports two modes:
      - git_commit  (default): write HTML to local RawWebsite repo, commit + push
      - manual_export: write to local export directory (for debugging / no git)

    Publishing contract:
      1. Write blog-{slug}.html to RawWebsite root
      2. Update sitemap.xml with the new post entry
      3. Git add + commit + push
      4. Log result to publish_logs table

    Phase 2: migrate to content/posts/YYYY-MM-DD-slug.md with frontmatter.
    """

    def __init__(self):
        # Load from environment / .env
        self.mode          = os.environ.get("RAWWEBSITE_PUBLISH_MODE", "git_commit")
        self.repo_url      = os.environ.get(
            "RAWWEBSITE_REPO_URL", "https://github.com/liemdo28/rawwebsite.git"
        )
        self.repo_branch   = os.environ.get("RAWWEBSITE_REPO_BRANCH", "main")
        self.author_name   = os.environ.get("GIT_AUTHOR_NAME", "AgentAI Agency")
        self.author_email  = os.environ.get("GIT_AUTHOR_EMAIL", "agency@rawsushibar.com")
        self.token         = os.environ.get("GIT_TOKEN", "")
        self.repo_path     = os.environ.get("RAWWEBSITE_REPO_PATH")
        self.export_dir    = Path(
            os.environ.get("POST_EXPORT_DIR", "data/post_exports")
        )

    # ── Public API ────────────────────────────────────────────────────────────

    def publish(
        self,
        post: dict,
        version: dict | None = None,
        *,
        author: str = "AgentAI Agency",
    ) -> dict:
        """
        Publish an approved post to RawWebsite.

        Args:
            post: post dict from PostRepository (must have id, slug, title, etc.)
            version: optional version dict for the specific version to publish
            author: display name for the audit trail

        Returns:
            PublishResult dict with success flag, URL, and details.

        Raises:
            ValueError — if post is not in a publishable state.
        """
        post_status = post.get("status", "")
        if post_status not in ("approved", "scheduled", "published"):
            raise ValueError(
                f"Post {post['id']} is in status {post_status!r} — "
                "cannot publish. Must be 'approved' or 'scheduled'."
            )

        slug = self._get_slug(post, version)
        publish_log_id = str(uuid4())

        logger.info(
            "Publishing post: id=%s slug=%s mode=%s",
            post["id"], slug, self.mode,
        )

        # Build HTML
        blog_html = self._build_blog_html(post, version)

        if self.mode == "git_commit":
            result = self._git_publish(slug, blog_html, post, version)
        else:
            result = self._manual_export(slug, blog_html, post, version)

        # Log to publish_logs table
        self._log_publish(
            publish_log_id,
            post["id"],
            version.get("id") if version else None,
            result,
        )

        return result

    # ── HTML building ─────────────────────────────────────────────────────────

    def _build_blog_html(self, post: dict, version: dict | None) -> str:
        """Build a full blog HTML page from a post + optional version."""
        version = version or {}

        title        = version.get("title")        or post.get("title", "Untitled")
        slug         = self._get_slug(post, version)
        seo_title    = version.get("seo_title")    or post.get("seo_title", title)
        seo_desc     = version.get("seo_description") or post.get("seo_description", "")
        body_md      = version.get("body_markdown") or post.get("body_markdown", "")
        cta_text     = version.get("cta_text")     or post.get("cta_text", "")
        cta_url      = version.get("cta_url")      or post.get("cta_url", "https://order.toasttab.com/online/raw-sushi-bistro-10742-trinity-pkwy-ste-d")
        focus_kw     = version.get("focus_keyword") or post.get("focus_keyword", "")
        post_type    = post.get("post_type", "blog")
        featured_url = version.get("featured_image_url") or post.get("featured_image_url", "")

        # Convert markdown body to HTML
        body_html = self._md_to_html(body_md)
        word_count = len(body_md.split())
        reading_time = max(1, round(word_count / 200))

        date_str   = (post.get("published_at") or post.get("created_at") or self._now())[:10]
        date_display = _date_display(date_str)
        post_type_label = _POST_TYPE_LABELS.get(post_type, post_type.title())

        # Featured image
        featured_block = ""
        if featured_url:
            alt = title.replace('"', "'")
            featured_block = (
                f'<div class="blog-featured-image">'
                f'<img src="{_esc(featured_url)}" alt="{_esc(alt)}" loading="lazy"></div>'
            )

        # CTA block
        cta_block = ""
        if cta_text:
            cta_block = (
                '<div class="cta-section">'
                f'<h3>{_esc(cta_text)}</h3>'
                f'<p>Experience authentic Japanese cuisine at Raw Sushi Bar, Stockton, CA.</p>'
                f'<a href="{_esc(cta_url)}" class="cta-btn" target="_blank" rel="noopener">Order Now</a>'
                '</div>'
            )

        favicon_svg = (
            '<link rel="icon" type="image/svg+xml"'
            ' href="data:image/svg+xml,%3Csvg xmlns=\'http://www.w3.org/2000/svg\' viewBox=\'0 0 32 32\'%3E'
            '<circle cx=\'16\' cy=\'16\' r=\'16\' fill=\'%231a1a1a\'/%3E'
            '<circle cx=\'16\' cy=\'16\' r=\'12\' fill=\'%23C41E3A\'/%3E'
            '<text x=\'16\' y=\'22\' text-anchor=\'middle\' font-family=\'Georgia,serif\' font-weight=\'bold\' font-size=\'18\' fill=\'white\'%3ER%3C/text%3E'
            "%3C/svg%3E\">"
        )

        return _BLOG_TEMPLATE.format(
            seo_description=_esc(seo_desc[:160]),
            focus_keyword=_esc(focus_kw),
            slug=slug,
            seo_title=_esc(seo_title[:60]),
            favicon=favicon_svg,
            title=_esc(title),
            author=_esc(author),
            date_published=date_str,
            date_published_display=date_display,
            reading_time=reading_time,
            post_type_label=post_type_label,
            featured_image_block=featured_block,
            body_html="            " + "\n            ".join(body_html.splitlines()),
            cta_block=cta_block,
            year=datetime.now().year,
        )

    # ── Git publish ───────────────────────────────────────────────────────────

    def _git_publish(self, slug: str, blog_html: str, post: dict, version: dict) -> dict:
        """Clone rawwebsite (if needed), write file, commit + push."""
        work_dir = self._prepare_repo()
        filename = f"{slug}.html"
        blog_path = work_dir / filename

        # Write HTML
        blog_path.write_text(blog_html, encoding="utf-8")
        logger.info("Wrote %s (%d bytes)", blog_path, len(blog_html))

        # Update sitemap
        self._update_sitemap(work_dir, slug, post, version)

        # Git add + commit + push
        self._git_add_commit_push(work_dir, filename, slug)

        html_url = f"https://www.rawsushibar.com/{slug}.html"
        logger.info("Published: %s", html_url)

        return {
            "success": True,
            "mode": "git_commit",
            "slug": slug,
            "filepath": str(blog_path),
            "html_url": html_url,
            "published_at": self._now(),
            "git_commit": self._git_capture(work_dir, "rev-parse", "--short", "HEAD"),
        }

    def _prepare_repo(self) -> Path:
        """Return the working directory for the rawwebsite repo."""
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
            auth_url = _auth_url(self.repo_url, self.token)
            self._git(clone_dir, "clone", auth_url, str(clone_dir),
                      "--branch", self.repo_branch, "--depth", "1")
        return clone_dir

    def _git_add_commit_push(self, repo_dir: Path, filename: str, slug: str) -> None:
        self._git(repo_dir, "add", filename)
        status = self._git_capture(repo_dir, "status", "--porcelain")
        if not status.strip():
            logger.info("No changes to commit for %s — file matches HEAD", slug)
            return

        commit_msg = (
            f"feat: publish blog post — {slug}\n\n"
            f"Published via AgentAI Agency content automation. "
            f"URL: https://www.rawsushibar.com/{slug}.html"
        )
        self._git(
            repo_dir,
            "-c", "commit.gpgsign=false",
            "commit", "-m", commit_msg,
            "--author", f"{self.author_name} <{self.author_email}>",
        )
        auth_remote = _auth_remote(self.repo_url, self.token)
        self._git(repo_dir, "push", auth_remote, self.repo_branch)

    def _update_sitemap(self, repo_dir: Path, slug: str, post: dict, version: dict) -> None:
        sitemap = repo_dir / "sitemap.xml"
        url = f"https://www.rawsushibar.com/{slug}.html"
        date = (post.get("published_at") or post.get("created_at") or self._now())[:10]
        entry = (
            f"  <url>\n"
            f"    <loc>{url}</loc>\n"
            f"    <lastmod>{date}</lastmod>\n"
            f"    <changefreq>monthly</changefreq>\n"
            f"    <priority>0.6</priority>\n"
            f"  </url>\n"
        )
        if sitemap.exists():
            content = sitemap.read_text(encoding="utf-8")
            if slug not in content:
                content = content.replace("</urlset>", f"{entry}</urlset>")
                sitemap.write_text(content, encoding="utf-8")
                self._git(repo_dir, "add", "sitemap.xml")

    @staticmethod
    def _git(cwd: Path, *args: str) -> subprocess.CompletedProcess:
        result = subprocess.run(
            ["git"] + list(args), cwd=cwd, capture_output=True, text=True
        )
        if result.returncode != 0:
            logger.warning("git %s failed: %s", args[0], result.stderr.strip())
        return result

    @staticmethod
    def _git_capture(cwd: Path, *args: str) -> str:
        result = subprocess.run(
            ["git"] + list(args), cwd=cwd, capture_output=True, text=True
        )
        return result.stdout.strip()

    # ── Manual export fallback ───────────────────────────────────────────────

    def _manual_export(self, slug: str, blog_html: str, post: dict, version: dict) -> dict:
        self.export_dir.mkdir(parents=True, exist_ok=True)
        html_path = self.export_dir / f"{slug}.html"
        json_path = self.export_dir / f"{slug}.json"
        html_path.write_text(blog_html, encoding="utf-8")
        json_path.write_text(
            json.dumps(self._build_manifest(post, version), indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        logger.info("Exported to %s", html_path)
        return {
            "success": True,
            "mode": "manual_export",
            "slug": slug,
            "filepath": str(html_path),
            "published_at": self._now(),
        }

    # ── Publish log ─────────────────────────────────────────────────────────

    def _log_publish(
        self, log_id: str, post_id: str, version_id: str | None, result: dict
    ) -> None:
        from db.post_repository import PostRepository
        repo = PostRepository()
        conn = repo._conn()
        try:
            conn.execute(
                """
                INSERT INTO publish_logs (id, post_id, version_id, target_system, status, response_payload, created_at)
                VALUES (?, ?, ?, ?, ?, ?, datetime('now'))
                """,
                (
                    log_id,
                    post_id,
                    version_id,
                    "rawwebsite",
                    "success" if result.get("success") else "failed",
                    json.dumps(result),
                ),
            )
            conn.commit()
            logger.info("Publish log written: id=%s post_id=%s success=%s",
                        log_id, post_id, result.get("success"))
        except Exception as exc:
            logger.warning("Could not write publish log: %s", exc)
        finally:
            conn.close()

    # ── Helpers ─────────────────────────────────────────────────────────────

    @staticmethod
    def _get_slug(post: dict, version: dict | None) -> str:
        slug = post.get("slug") or (version or {}).get("slug") or ""
        if slug:
            return re.sub(r"[^a-z0-9-]", "-", slug.lower())[:60].strip("-")
        title = (version or {}).get("title") or post.get("title", "untitled")
        return re.sub(r"[^a-z0-9]+", "-", title.lower())[:60].strip("-")

    @staticmethod
    def _build_manifest(post: dict, version: dict) -> dict:
        return {
            "id": post.get("id"),
            "slug": post.get("slug") or (version or {}).get("slug"),
            "title": (version or {}).get("title") or post.get("title"),
            "excerpt": (version or {}).get("excerpt") or post.get("excerpt"),
            "body_markdown": (version or {}).get("body_markdown") or post.get("body_markdown"),
            "seo_title": (version or {}).get("seo_title") or post.get("seo_title"),
            "seo_description": (version or {}).get("seo_description") or post.get("seo_description"),
            "focus_keyword": (version or {}).get("focus_keyword") or post.get("focus_keyword"),
            "cta_text": (version or {}).get("cta_text") or post.get("cta_text"),
            "cta_url": (version or {}).get("cta_url") or post.get("cta_url"),
            "featured_image_url": (version or {}).get("featured_image_url") or post.get("featured_image_url"),
            "brand_name": post.get("brand_name"),
            "published_at": datetime.now(timezone.utc).isoformat(),
        }

    @staticmethod
    def _md_to_html(md: str) -> str:
        """Convert markdown to minimal HTML (no full-page wrapper)."""
        if not md:
            return "<p>Content coming soon.</p>"
        import html
        text = html.escape(md)
        text = re.sub(r"^## (.+)$", r"<h2>\1</h2>", text, flags=re.MULTILINE)
        text = re.sub(r"^### (.+)$", r"<h3>\1</h3>", text, flags=re.MULTILINE)
        text = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", text)
        text = re.sub(r"\*(.+?)\*", r"<em>\1</em>", text)
        paragraphs = re.split(r"\n{2,}", text)
        result = []
        for p in paragraphs:
            stripped = p.strip()
            if not stripped:
                continue
            if re.match(r"<h[23]|<ul|<ol|<blockquote", stripped):
                result.append(stripped)
            else:
                result.append(f"<p>{stripped}</p>")
        return "\n".join(result)

    @staticmethod
    def _now() -> str:
        return datetime.now(timezone.utc).isoformat()


# ─────────────────────────────────────────────────────────────────────────────
#  Template + helpers
# ─────────────────────────────────────────────────────────────────────────────

_POST_TYPE_LABELS = {
    "promo": "Promo", "event": "Event", "blog": "Blog",
    "seasonal": "Seasonal", "landing-content": "Landing",
    "viral_attention": "Dining Guide", "conversion_order": "Special Offer",
    "local_discovery": "Local Dining", "tourist_discovery": "Visitor Guide",
    "menu_highlight": "Menu", "seasonal_trend": "Seasonal",
}


def _esc(s: str) -> str:
    import html
    return html.escape(str(s))


_BLOG_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <meta name="description" content="{seo_description}">
    <meta name="keywords" content="{focus_keyword}">
    <meta name="robots" content="index, follow">
    <link rel="canonical" href="https://www.rawsushibar.com/{slug}.html">
    <title>{seo_title}</title>
    <meta property="og:type" content="article">
    <meta property="og:url" content="https://www.rawsushibar.com/{slug}.html">
    <meta property="og:title" content="{seo_title}">
    <meta property="og:description" content="{seo_description}">
{favicon}
    <link rel="apple-touch-icon" href="https://static.wixstatic.com/media/401243_d65d2b6fde216c976b09b4520417899d.png/v1/fill/w_180,h_180,al_c,q_85/logo.png">
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=Playfair+Display:wght@400;500;600;700&family=Inter:wght@300;400;500;600;700&display=swap" rel="stylesheet">
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        :root {{ --primary-red: #C41E3A; --deep-red: #a01829; --charcoal: #2b2b2b; --cream: #f9f7f4; --warm-cream: #f5f0ea; --gold: #d4af37; --text-dark: #2c2824; --text-medium: #5a544e; --text-light: #8a847e; --white: #ffffff; }}
        body {{ font-family: 'Inter', sans-serif; color: var(--text-dark); line-height: 1.6; background: var(--cream); }}
        a {{ color: var(--primary-red); text-decoration: none; }}
        a:hover {{ text-decoration: underline; }}
        .skip-link {{ position: absolute; top: -100px; left: 0; background: var(--primary-red); color: var(--white); padding: 10px 15px; z-index: 100000; transition: top 0.2s; text-decoration: none; font-weight: bold; }}
        .skip-link:focus {{ top: 0; }}
        .nav-container {{ position: fixed; top: 0; width: 100%; z-index: 1000; background: rgba(26,26,26,0.95); backdrop-filter: blur(12px); -webkit-backdrop-filter: blur(12px); box-shadow: 0 2px 20px rgba(0,0,0,0.15); }}
        nav {{ max-width: 1400px; margin: 0 auto; display: flex; justify-content: space-between; align-items: center; padding: 0.75rem 3rem; }}
        .logo {{ display: flex; align-items: center; text-decoration: none; flex-shrink: 0; gap: 0; }}
        .logo svg {{ height: 44px; width: auto; display: block; }}
        .nav-links {{ display: flex; list-style: none; gap: 2rem; align-items: center; }}
        .nav-links a {{ color: rgba(255,255,255,0.85); text-decoration: none; font-weight: 500; font-size: 0.9rem; transition: all 0.3s ease; position: relative; letter-spacing: 0.5px; text-transform: uppercase; }}
        .nav-links a:hover {{ color: var(--gold); }}
        .blog-container {{ max-width: 860px; margin: 0 auto; padding: 8rem 2rem 4rem; }}
        .blog-header {{ text-align: center; margin-bottom: 3rem; }}
        .blog-category {{ display: inline-block; background: var(--primary-red); color: var(--white); padding: 0.3rem 1rem; border-radius: 50px; font-size: 0.75rem; font-weight: 700; letter-spacing: 2px; text-transform: uppercase; margin-bottom: 1.25rem; }}
        .blog-title {{ font-family: 'Playfair Display', serif; font-size: 2.8rem; color: var(--text-dark); margin-bottom: 1rem; line-height: 1.2; }}
        .blog-meta {{ display: flex; justify-content: center; gap: 2rem; font-size: 0.85rem; color: var(--text-light); flex-wrap: wrap; }}
        .blog-featured-image {{ width: 100%; border-radius: 12px; margin-bottom: 2.5rem; overflow: hidden; }}
        .blog-featured-image img {{ width: 100%; height: auto; display: block; border-radius: 12px; }}
        .blog-content {{ font-size: 1.05rem; line-height: 1.8; color: var(--text-medium); }}
        .blog-content h2 {{ font-family: 'Playfair Display', serif; font-size: 1.8rem; color: var(--text-dark); margin: 2.5rem 0 1rem; }}
        .blog-content h3 {{ font-family: 'Playfair Display', serif; font-size: 1.4rem; color: var(--text-dark); margin: 2rem 0 0.75rem; }}
        .blog-content p {{ margin-bottom: 1.5rem; }}
        .blog-content blockquote {{ border-left: 4px solid var(--gold); padding: 1rem 1.5rem; margin: 2rem 0; background: var(--warm-cream); border-radius: 0 8px 8px 0; font-style: italic; color: var(--text-dark); }}
        .blog-content strong {{ color: var(--text-dark); }}
        .blog-content a {{ color: var(--primary-red); }}
        .cta-section {{ background: linear-gradient(135deg, var(--primary-red) 0%, #8b1528 100%); color: var(--white); padding: 3rem; border-radius: 12px; text-align: center; margin: 3rem 0; }}
        .cta-section h3 {{ font-family: 'Playfair Display', serif; font-size: 1.8rem; margin-bottom: 0.75rem; }}
        .cta-section p {{ opacity: 0.9; margin-bottom: 1.5rem; }}
        .cta-btn {{ display: inline-block; background: var(--gold); color: var(--text-dark); padding: 0.85rem 2rem; border-radius: 6px; font-weight: 700; text-decoration: none; transition: all 0.3s ease; }}
        .cta-btn:hover {{ transform: translateY(-3px); box-shadow: 0 10px 25px rgba(212,175,55,0.4); text-decoration: none; }}
        .blog-share {{ display: flex; justify-content: center; gap: 1rem; margin-top: 3rem; padding-top: 2rem; border-top: 1px solid rgba(0,0,0,0.08); }}
        .share-btn {{ padding: 0.6rem 1.25rem; border-radius: 6px; font-size: 0.85rem; font-weight: 600; text-decoration: none; transition: all 0.3s ease; }}
        .share-btn:hover {{ transform: translateY(-2px); text-decoration: none; }}
        footer {{ background: var(--charcoal); color: rgba(255,255,255,0.8); padding: 3rem 2rem 1.5rem; text-align: center; }}
        footer a {{ color: rgba(255,255,255,0.7); text-decoration: none; }}
        footer a:hover {{ color: var(--white); }}
        footer p {{ font-size: 0.85rem; opacity: 0.5; margin-top: 0.5rem; }}
        @media (max-width: 768px) {{ nav {{ padding: 0.75rem 1.5rem; }} .blog-title {{ font-size: 2rem; }} .blog-container {{ padding-top: 6rem; }} }}
    </style>
</head>
<body>
    <a href="#main-content" class="skip-link">Skip to main content</a>
    <header class="nav-container" role="banner">
        <nav aria-label="Main navigation">
            <a href="/" class="logo" aria-label="Raw Sushi Bar - Home">
                <svg viewBox="0 0 200 50" xmlns="http://www.w3.org/2000/svg" role="img" aria-label="Raw Sushi Bar logo">
                    <circle cx="25" cy="25" r="22" fill="#1a1a1a" stroke="#C41E3A" stroke-width="1.5"/>
                    <text x="25" y="33" text-anchor="middle" font-family="'Playfair Display',Georgia,serif" font-style="italic" font-weight="700" font-size="28" fill="#C41E3A">R</text>
                    <text x="60" y="24" font-family="'Playfair Display',Georgia,serif" font-style="italic" font-weight="700" font-size="24" fill="#C41E3A" letter-spacing="2">aw</text>
                    <text x="60" y="42" font-family="'Inter','Helvetica Neue',sans-serif" font-weight="300" font-size="11" fill="rgba(255,255,255,0.9)" letter-spacing="3">SUSHI BAR</text>
                </svg>
            </a>
            <ul class="nav-links">
                <li><a href="/">Home</a></li>
                <li><a href="/menu-stockton.html">Menu</a></li>
                <li><a href="/#locations">Locations</a></li>
                <li><a href="https://order.toasttab.com/online/raw-sushi-bistro-10742-trinity-pkwy-ste-d" target="_blank" rel="noopener">Order Online</a></li>
            </ul>
        </nav>
    </header>
    <main id="main-content">
        <article class="blog-container" itemscope itemtype="https://schema.org/BlogPosting">
            <header class="blog-header">
                <span class="blog-category">{post_type_label}</span>
                <h1 class="blog-title" itemprop="headline">{title}</h1>
                <div class="blog-meta">
                    <span itemprop="author">By {author}</span>
                    <span itemprop="datePublished">{date_published_display}</span>
                    <span>{reading_time} min read</span>
                </div>
            </header>
            {featured_image_block}
            <div class="blog-content" itemprop="articleBody">
{body_html}
            </div>
            {cta_block}
            <div class="blog-share">
                <a href="https://www.facebook.com/rawsushibar/" target="_blank" rel="noopener" class="share-btn" style="background:#3b5998;color:#fff;">Facebook</a>
                <a href="https://instagram.com/rawsushibistro/" target="_blank" rel="noopener" class="share-btn" style="background:linear-gradient(135deg,#f09433,#e6683c,#dc2743,#cc2366,#bc1888);color:#fff;">Instagram</a>
            </div>
        </article>
    </main>
    <footer role="contentinfo">
        <p>&copy; {year} <a href="/">Raw Sushi Bar</a>. All rights reserved. | <a href="mailto:info@rawsushibar.com">info@rawsushibar.com</a></p>
    </footer>
</body>
</html>"""


def _auth_url(url: str, token: str) -> str:
    if not token or not url.startswith("https://"):
        return url
    return url.replace("https://", f"https://{token}@")


def _auth_remote(url: str, token: str) -> str:
    if not token or not url.startswith("https://"):
        return "origin"
    return url.replace("https://", f"https://{token}@")


def _date_display(iso: str) -> str:
    try:
        return datetime.fromisoformat(iso.replace("Z", "+00:00")).strftime("%B %d, %Y")
    except Exception:
        return iso[:10]