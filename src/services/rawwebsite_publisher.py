"""
RawWebsitePublisher — P2 stub for exporting approved posts.

Supports three modes:
  - manual_export (default): writes an HTML file to a local export directory
  - api_publish: calls rawwebsite CMS API endpoint (requires configuration)
  - git_commit: writes HTML to local rawwebsite repo and commits via Git

Git publish requires:
  RAWWEBSITE_REPO_PATH  = /path/to/rawwebsite  (local clone of the repo)
  RAWWEBSITE_GIT_BRANCH = main                (branch to push to)
  GIT_AUTHOR_NAME  = "AgentAI Agency"
  GIT_AUTHOR_EMAIL = "agency@rawsushibar.com"
  (Uses system git with a GitHub PAT in git config credential helper)
"""
from __future__ import annotations

import html as _html
import json
import logging
import os
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger(__name__)

_POST_TYPE_LABELS = {
    "promo": "Promo",
    "event": "Event",
    "blog": "Blog",
    "seasonal": "Seasonal",
    "landing-content": "Landing",
}


def _md_to_html(md: str) -> str:
    """Convert markdown to minimal HTML."""
    if not md:
        return ""
    html = _html.escape(md)
    # Block quotes
    html = re.sub(r"^&gt; (.+)$", r"<blockquote>\1</blockquote>", html, flags=re.MULTILINE)
    # H2
    html = re.sub(r"^## (.+)$", r"<h2>\1</h2>", html, flags=re.MULTILINE)
    # H3
    html = re.sub(r"^### (.+)$", r"<h3>\1</h3>", html, flags=re.MULTILINE)
    # Bold
    html = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", html)
    # Italic
    html = re.sub(r"\*(.+?)\*", r"<em>\1</em>", html)
    # Unordered list items
    html = re.sub(r"^- (.+)$", r"<li>\1</li>", html, flags=re.MULTILINE)
    html = re.sub(r"(<li>.*</li>\n?)+", lambda m: f"<ul>{m.group(0)}</ul>", html, flags=re.DOTALL)
    # Ordered list items
    html = re.sub(r"^\d+\. (.+)$", r"<li>\1</li>", html, flags=re.MULTILINE)
    # Paragraphs (double newlines)
    paragraphs = re.split(r"\n{2,}", html)
    html = "\n".join(
        f"<p>{p.strip()}</p>" if not re.match(r"<h[23]|</?ul|</?blockquote", p.strip()) else p.strip()
        for p in paragraphs if p.strip()
    )
    return html


def _estimate_reading_time(text: str) -> int:
    words = len(text.split())
    return max(1, round(words / 200))


BLOG_TEMPLATE = """<!DOCTYPE html>
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

    <script type="application/ld+json">
    {{
      "@context": "https://schema.org",
      "@type": "BlogPosting",
      "mainEntityOfPage": {{
        "@type": "WebPage",
        "@id": "https://www.rawsushibar.com/{slug}.html"
      }},
      "headline": "{title}",
      "description": "{seo_description}",
      "author": {{
        "@type": "Person",
        "name": "{author}"
      }},
      "publisher": {{
        "@type": "Organization",
        "name": "{brand_name}",
        "logo": {{
          "@type": "ImageObject",
          "url": "https://www.rawsushibar.com/images/logo.png"
        }}
      }},
      "datePublished": "{date_published}",
      "dateModified": "{date_published}"
    }}
    </script>

    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=Playfair+Display:wght@400;500;600;700&family=Inter:wght@300;400;500;600;700&display=swap" rel="stylesheet">

    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        .skip-link {{ position: absolute; top: -100px; left: 0; background: var(--primary-red); color: var(--white); padding: 10px 15px; z-index: 100000; transition: top 0.2s; text-decoration: none; font-weight: bold; }}
        .skip-link:focus {{ top: 0; }}
        *:focus-visible {{ outline: 3px solid var(--primary-red) !important; outline-offset: 3px !important; }}
        :root {{
            --primary-red: #C41E3A;
            --deep-red: #a01829;
            --charcoal: #2b2b2b;
            --cream: #f9f7f4;
            --warm-cream: #f5f0ea;
            --gold: #d4af37;
            --teal: #1a4d4d;
            --white: #ffffff;
            --text-dark: #2c2824;
            --text-medium: #5a544e;
            --text-light: #8a847e;
        }}
        body {{ font-family: 'Inter', sans-serif; color: var(--text-dark); line-height: 1.6; background: var(--cream); }}
        a {{ color: var(--primary-red); text-decoration: none; }}
        a:hover {{ text-decoration: underline; }}
        .skip-nav {{ position: absolute; top: -100%; left: 0; background: var(--primary-red); color: white; padding: 0.75rem 1.5rem; z-index: 10000; font-weight: 600; text-decoration: none; }}
        .skip-nav:focus {{ top: 0; }}
        .nav-container {{ position: fixed; top: 0; width: 100%; z-index: 1000; background: rgba(26,26,26,0.95); backdrop-filter: blur(12px); -webkit-backdrop-filter: blur(12px); box-shadow: 0 2px 20px rgba(0,0,0,0.15); }}
        nav {{ max-width: 1400px; margin: 0 auto; display: flex; justify-content: space-between; align-items: center; padding: 0.75rem 3rem; }}
        .logo {{ display: flex; align-items: center; text-decoration: none; flex-shrink: 0; gap: 0; }}
        .logo svg {{ height: 44px; width: auto; display: block; }}
        .nav-links {{ display: flex; list-style: none; gap: 2rem; align-items: center; }}
        .nav-links a {{ color: rgba(255,255,255,0.85); text-decoration: none; font-weight: 500; font-size: 0.9rem; transition: all 0.3s ease; position: relative; letter-spacing: 0.5px; text-transform: uppercase; }}
        .nav-links a:hover {{ color: var(--gold); }}
        .nav-links a::after {{ content: ''; position: absolute; bottom: -4px; left: 0; width: 0; height: 2px; background: var(--gold); transition: width 0.3s ease; }}
        .nav-links a:hover::after {{ width: 100%; }}
        .blog-container {{ max-width: 860px; margin: 0 auto; padding: 8rem 2rem 4rem; }}
        .blog-header {{ text-align: center; margin-bottom: 3rem; }}
        .blog-category {{ display: inline-block; background: var(--primary-red); color: var(--white); padding: 0.3rem 1rem; border-radius: 50px; font-size: 0.75rem; font-weight: 700; letter-spacing: 2px; text-transform: uppercase; margin-bottom: 1.25rem; }}
        .blog-title {{ font-family: 'Playfair Display', serif; font-size: 2.8rem; color: var(--text-dark); margin-bottom: 1rem; line-height: 1.2; }}
        .blog-meta {{ display: flex; justify-content: center; gap: 2rem; font-size: 0.85rem; color: var(--text-light); flex-wrap: wrap; }}
        .blog-meta span {{ display: flex; align-items: center; gap: 0.4rem; }}
        .blog-featured-image {{ width: 100%; border-radius: 12px; margin-bottom: 2.5rem; overflow: hidden; }}
        .blog-featured-image img {{ width: 100%; height: auto; display: block; border-radius: 12px; }}
        .blog-content {{ font-size: 1.05rem; line-height: 1.8; color: var(--text-medium); }}
        .blog-content h2 {{ font-family: 'Playfair Display', serif; font-size: 1.8rem; color: var(--text-dark); margin: 2.5rem 0 1rem; }}
        .blog-content h3 {{ font-family: 'Playfair Display', serif; font-size: 1.4rem; color: var(--text-dark); margin: 2rem 0 0.75rem; }}
        .blog-content p {{ margin-bottom: 1.5rem; }}
        .blog-content ul, .blog-content ol {{ margin: 1rem 0 1.5rem 1.5rem; }}
        .blog-content li {{ margin-bottom: 0.5rem; }}
        .blog-content blockquote {{ border-left: 4px solid var(--gold); padding: 1rem 1.5rem; margin: 2rem 0; background: var(--warm-cream); border-radius: 0 8px 8px 0; font-style: italic; color: var(--text-dark); }}
        .blog-content strong {{ color: var(--text-dark); }}
        .blog-content img {{ max-width: 100%; border-radius: 8px; }}
        .blog-content a {{ color: var(--primary-red); }}
        .cta-section {{ background: linear-gradient(135deg, var(--primary-red) 0%, #8b1528 100%); color: var(--white); padding: 3rem; border-radius: 12px; text-align: center; margin: 3rem 0; }}
        .cta-section h3 {{ font-family: 'Playfair Display', serif; font-size: 1.8rem; margin-bottom: 0.75rem; }}
        .cta-section p {{ opacity: 0.9; margin-bottom: 1.5rem; }}
        .cta-btn {{ display: inline-block; background: var(--gold); color: var(--warm-black, #1a1a1a); padding: 0.85rem 2rem; border-radius: 6px; font-weight: 700; text-decoration: none; transition: all 0.3s ease; }}
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
    <a href="#main-content" class="skip-nav">Skip to main content</a>

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


class RawWebsitePublisher:
    """
    Publish or export approved posts for rawwebsite.

    Supports three modes:
      - git_commit  (default): clone rawwebsite repo, write blog HTML, commit & push.
                               Falls back to git if local repo not found.
      - manual_export: writes HTML + JSON to a local directory (for debugging).
      - api_publish: POST to rawwebsite CMS API (requires RAWWEBSITE_API_ENDPOINT).

    Required env vars for git_commit mode:
      RAWWEBSITE_PUBLISH_MODE  = git_commit
      RAWWEBSITE_REPO_URL      = https://github.com/liemdo28/rawwebsite.git
      RAWWEBSITE_REPO_BRANCH   = main
      GIT_AUTHOR_NAME          = AgentAI Agency
      GIT_AUTHOR_EMAIL        = agency@rawsushibar.com
      GIT_TOKEN                = your GitHub PAT (for push auth)
      RAWWEBSITE_REPO_PATH     = /path/to/local/clone  (optional — auto-clones if missing)

    The repo is cloned freshly each time (or reused if RAWWEBSITE_REPO_PATH exists and
    is a valid git repo). After writing, changes are committed and pushed.
    On success the published HTML lives at https://www.rawsushibar.com/{slug}.html
    """

    def __init__(self):
        self.mode = os.environ.get("RAWWEBSITE_PUBLISH_MODE", "git_commit")
        self.export_dir = Path(os.environ.get("POST_EXPORT_DIR", "/tmp/post_exports"))
        self.repo_url = os.environ.get("RAWWEBSITE_REPO_URL", "https://github.com/liemdo28/rawwebsite.git")
        self.repo_branch = os.environ.get("RAWWEBSITE_REPO_BRANCH", "main")
        self.author_name = os.environ.get("GIT_AUTHOR_NAME", "AgentAI Agency")
        self.author_email = os.environ.get("GIT_AUTHOR_EMAIL", "agency@rawsushibar.com")
        self.token = os.environ.get("GIT_TOKEN", "")
        self.api_endpoint = os.environ.get("RAWWEBSITE_API_ENDPOINT")
        self.api_key = os.environ.get("RAWWEBSITE_API_KEY")
        self._repo_path = os.environ.get("RAWWEBSITE_REPO_PATH")
        self._commit_msg_prefix = os.environ.get("GIT_COMMIT_MSG_PREFIX", "feat: publish blog post")

    # ── Public API ────────────────────────────────────────────────────────────

    def publish(self, post: dict, version: dict | None = None) -> dict:
        """
        Export or publish the post.

        Returns a dict with:
          - mode: publish mode used
          - slug: post slug
          - html_url: final URL on the live site
          - published_at: ISO timestamp
        """
        version = version or {}
        slug = self._get_slug(post, version)
        author = post.get("author") or post.get("created_by") or "AgentAI Agency"
        date_str = post.get("published_at") or post.get("created_at") or datetime.now(timezone.utc).isoformat()
        date_display = _date_display(date_str)
        post_type = post.get("post_type", "blog")
        brand_name = post.get("brand_name", "Raw Sushi Bar")

        body_md = version.get("body_markdown") or post.get("body_markdown") or ""
        body_html = _md_to_html(body_md)
        reading_time = _estimate_reading_time(body_md)

        # Build featured image block
        img_url = version.get("featured_image_url") or post.get("featured_image_url") or ""
        featured_block = (
            f'<div class="blog-featured-image"><img src="{_html.escape(img_url)}" alt="{_html.escape(version.get("title") or post.get("title") or "")}" loading="lazy"></div>'
            if img_url else ""
        )

        # Build CTA block
        cta_text = version.get("cta_text") or post.get("cta_text") or ""
        cta_url = version.get("cta_url") or post.get("cta_url") or "https://order.toasttab.com/online/raw-sushi-bistro-10742-trinity-pkwy-ste-d"
        cta_block = ""
        if cta_text:
            cta_block = (
                '<div class="cta-section">'
                f"<h3>{_html.escape(cta_text)}</h3>"
                f'<p>Experience authentic Japanese cuisine at Raw Sushi Bar.</p>'
                f'<a href="{_html.escape(cta_url)}" class="cta-btn" target="_blank" rel="noopener">Order Now</a>'
                "</div>"
            )

        favicon_block = (
            '<link rel="icon" type="image/svg+xml"'
            'href="data:image/svg+xml,%3Csvg xmlns=\'http://www.w3.org/2000/svg\' viewBox=\'0 0 32 32\'%3E'
            '<circle cx=\'16\' cy=\'16\' r=\'16\' fill=\'%231a1a1a\'/%3E'
            '<circle cx=\'16\' cy=\'16\' r=\'12\' fill=\'%23C41E3A\'/%3E'
            '<text x=\'16\' y=\'22\' text-anchor=\'middle\' font-family=\'Georgia,serif\' font-weight=\'bold\' font-size=\'18\' fill=\'white\'%3ER%3C/text%3E'
            "%3C/svg%3E\">"
        )

        # Render blog HTML from template
        blog_html = BLOG_TEMPLATE.format(
            seo_description=_html.escape(version.get("seo_description") or post.get("seo_description") or ""),
            focus_keyword=_html.escape(version.get("focus_keyword") or post.get("focus_keyword") or ""),
            slug=slug,
            seo_title=_html.escape(version.get("seo_title") or post.get("seo_title") or post.get("title") or "Untitled"),
            favicon=favicon_block,
            title=_html.escape(version.get("title") or post.get("title") or ""),
            author=_html.escape(author),
            brand_name=_html.escape(brand_name),
            date_published=date_str[:10],
            date_published_display=date_display,
            reading_time=reading_time,
            post_type_label=_POST_TYPE_LABELS.get(post_type, post_type.title()),
            featured_image_block=featured_block,
            body_html="            ".join(
                body_html.splitlines()
            ) if body_html else "            <p>Content coming soon.</p>",
            cta_block=cta_block,
            year=datetime.now().year,
        )

        if self.mode == "git_commit":
            return self._git_commit(slug, blog_html, post, version)
        if self.mode == "api_publish":
            return self._api_publish(post, version)
        return self._manual_export(slug, blog_html, post, version)

    # ── Git publish (main mode) ────────────────────────────────────────────────

    def _git_commit(self, slug: str, blog_html: str, post: dict, version: dict) -> dict:
        """Clone rawwebsite repo (if needed), write blog HTML, update sitemap, commit & push."""
        work_dir = self._prepare_repo()
        blog_path = work_dir / f"{slug}.html"
        blog_path.write_text(blog_html, encoding="utf-8")
        logger.info("Wrote blog HTML to %s", blog_path)

        # Update sitemap.xml
        self._update_sitemap(work_dir, slug, post, version)
        logger.info("Updated sitemap.xml")

        # Git add + commit + push
        self._git_add_commit_push(work_dir, f"{slug}.html", slug)
        html_url = f"https://www.rawsushibar.com/{slug}.html"
        logger.info("Published: %s", html_url)
        return {
            "mode": "git_commit",
            "slug": slug,
            "html_url": html_url,
            "published_at": datetime.now(timezone.utc).isoformat(),
        }

    def _prepare_repo(self) -> Path:
        """
        Return the working directory for the rawwebsite repo.

        Strategy:
          1. RAWWEBSITE_REPO_PATH exists + has .git  → use it
          2. Otherwise clone fresh to POST_EXPORT_DIR / rawwebsite_clone
        """
        if self._repo_path:
            candidate = Path(self._repo_path)
            if candidate.exists() and (candidate / ".git").exists():
                return candidate
            # Pull latest if it's a git repo but path env var changed
            if candidate.exists():
                self._git(candidate, "fetch", "origin", self.repo_branch)
                self._git(candidate, "checkout", self.repo_branch)
                self._git(candidate, "pull", "origin", self.repo_branch)
                return candidate
            # Fall through: clone fresh
        clone_dir = self.export_dir / "rawwebsite_clone"
        if clone_dir.exists():
            # Already cloned — pull latest
            self._git(clone_dir, "fetch", "origin", self.repo_branch)
            self._git(clone_dir, "checkout", self.repo_branch)
            self._git(clone_dir, "pull", "origin", self.repo_branch)
        else:
            clone_dir.mkdir(parents=True, exist_ok=True)
            auth_url = _auth_url(self.repo_url, self.token)
            self._git(clone_dir, "clone", auth_url, str(clone_dir), "--branch", self.repo_branch, "--depth", "1")
        return clone_dir

    def _git_add_commit_push(self, repo_dir: Path, file_rel_path: str, slug: str) -> None:
        """Stage file, commit with a descriptive message, push."""
        self._git(repo_dir, "add", file_rel_path)
        # Check if there are staged changes
        status_out = self._git_capture(repo_dir, "status", "--porcelain")
        if not status_out.strip():
            logger.info("No changes to commit for %s — file already matches HEAD", slug)
            return

        commit_msg = (
            f"{self._commit_msg_prefix}: {slug}\n\n"
            f"Published via AgentAI Agency. "
            f"URL: https://www.rawsushibar.com/{slug}.html"
        )
        self._git(repo_dir, "-c", "commit.gpgsign=false",
                  "commit", "-m", commit_msg,
                  "--author", f"{self.author_name} <{self.author_email}>")
        logger.info("Committed %s", slug)

        auth_remote = _auth_remote(self.repo_url, self.token)
        self._git(repo_dir, "push", auth_remote, self.repo_branch)
        logger.info("Pushed to %s/%s", self.repo_branch, slug)

    def _update_sitemap(self, repo_dir: Path, slug: str, post: dict, version: dict) -> None:
        """Append the new blog post to sitemap.xml if not already present."""
        sitemap = repo_dir / "sitemap.xml"
        url = f"https://www.rawsushibar.com/{slug}.html"
        date = (post.get("published_at") or post.get("created_at") or datetime.now(timezone.utc).isoformat())[:10]
        priority = "0.8" if post.get("post_type") == "landing-content" else "0.6"
        changefreq = "monthly"

        entry = (
            f"  <url>\n"
            f"    <loc>{url}</loc>\n"
            f"    <lastmod>{date}</lastmod>\n"
            f"    <changefreq>{changefreq}</changefreq>\n"
            f"    <priority>{priority}</priority>\n"
            f"  </url>\n"
        )

        if sitemap.exists():
            content = sitemap.read_text(encoding="utf-8")
            if slug not in content:
                # Insert before </urlset>
                content = content.replace("</urlset>", f"{entry}</urlset>")
                sitemap.write_text(content, encoding="utf-8")
        else:
            sitemap.write_text(
                f'<?xml version="1.0" encoding="UTF-8"?>\n'
                f'<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
                f"{entry}</urlset>\n",
                encoding="utf-8",
            )

    # ── Git helpers ────────────────────────────────────────────────────────────

    @staticmethod
    def _git(cwd: Path, *args: str) -> subprocess.CompletedProcess:
        result = subprocess.run(
            ["git", *args],
            cwd=cwd,
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            logger.warning("git %s failed: %s | %s", args[0], result.stderr, result.stdout)
        return result

    @staticmethod
    def _git_capture(cwd: Path, *args: str) -> str:
        result = subprocess.run(
            ["git", *args],
            cwd=cwd,
            capture_output=True,
            text=True,
        )
        return result.stdout

    # ── Fallback modes ─────────────────────────────────────────────────────────

    def _manual_export(self, slug: str, blog_html: str, post: dict, version: dict) -> dict:
        """Write post as HTML + JSON manifest to the export directory."""
        self.export_dir.mkdir(parents=True, exist_ok=True)
        html_path = self.export_dir / f"{slug}.html"
        json_path = self.export_dir / f"{slug}.json"
        html_path.write_text(blog_html, encoding="utf-8")
        json_path.write_text(json.dumps(self._build_manifest(post, version), indent=2, ensure_ascii=False), encoding="utf-8")
        return {
            "mode": "manual_export",
            "slug": slug,
            "html_path": str(html_path),
            "json_path": str(json_path),
            "published_at": datetime.now(timezone.utc).isoformat(),
        }

    def _api_publish(self, post: dict, version: dict) -> dict:
        """POST to rawwebsite CMS API."""
        if not self.api_endpoint:
            raise NotImplementedError(
                "RAWWEBSITE_API_ENDPOINT not configured. "
                "Set RAWWEBSITE_PUBLISH_MODE=git_commit or manual_export instead."
            )
        import urllib.request
        payload = json.dumps(self._build_manifest(post, version)).encode("utf-8")
        req = urllib.request.Request(
            self.api_endpoint,
            data=payload,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.api_key or ''}",
            },
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=30) as resp:
            body = resp.read().decode("utf-8")
            result = json.loads(body) if body else {}
        return {
            "mode": "api_publish",
            "slug": post.get("slug"),
            "api_response": result,
            "published_at": datetime.now(timezone.utc).isoformat(),
        }

    # ── Helpers ────────────────────────────────────────────────────────────────

    @staticmethod
    def _get_slug(post: dict, version: dict) -> str:
        slug = post.get("slug") or version.get("slug") or ""
        if slug:
            return re.sub(r"[^a-z0-9-]", "-", slug.lower())[:60].strip("-")
        # Fallback from title
        title = version.get("title") or post.get("title") or "untitled"
        return re.sub(r"[^a-z0-9]+", "-", title.lower())[:60].strip("-")

    @staticmethod
    def _build_manifest(post: dict, version: dict) -> dict:
        return {
            "id": post.get("id"),
            "slug": post.get("slug") or version.get("slug"),
            "title": version.get("title") or post.get("title"),
            "excerpt": version.get("excerpt") or post.get("excerpt"),
            "body_markdown": version.get("body_markdown") or post.get("body_markdown"),
            "body_html": version.get("body_html") or post.get("body_html"),
            "seo_title": version.get("seo_title") or post.get("seo_title"),
            "seo_description": version.get("seo_description") or post.get("seo_description"),
            "focus_keyword": version.get("focus_keyword") or post.get("focus_keyword"),
            "cta_text": version.get("cta_text") or post.get("cta_text"),
            "cta_url": version.get("cta_url") or post.get("cta_url"),
            "featured_image_url": version.get("featured_image_url") or post.get("featured_image_url"),
            "channel": post.get("channel"),
            "post_type": post.get("post_type"),
            "brand_name": post.get("brand_name"),
            "approved_by": post.get("approved_by"),
            "published_at": datetime.now(timezone.utc).isoformat(),
        }


def _auth_url(url: str, token: str) -> str:
    if not token:
        return url
    if url.startswith("https://"):
        return url.replace("https://", f"https://{token}@")


def _auth_remote(url: str, token: str) -> str:
    """Return remote URL with token embedded for push."""
    if not token:
        return "origin"
    if url.startswith("https://"):
        return url.replace("https://", f"https://{token}@")
    return "origin"


def _date_display(iso: str) -> str:
    """Convert 2026-04-13T... to 'April 13, 2026'."""
    try:
        return datetime.fromisoformat(iso.replace("Z", "+00:00")).strftime("%B %d, %Y")
    except Exception:
        return iso[:10]
