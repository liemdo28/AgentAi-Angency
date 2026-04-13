"""
RawWebsitePublisher — P2 stub for exporting approved posts.

Supports two modes:
  - manual_export (default): writes an HTML file to a local export directory
  - api_publish: calls rawwebsite CMS API endpoint (requires configuration)
"""
from __future__ import annotations

import html as _html
import json
import os
from datetime import datetime, timezone
from pathlib import Path


class RawWebsitePublisher:
    """Publish or export approved posts for rawwebsite."""

    mode: str = os.environ.get("RAWWEBSITE_PUBLISH_MODE", "manual_export")
    export_dir: Path = Path(os.environ.get("POST_EXPORT_DIR", "/tmp/post_exports"))
    api_endpoint: str | None = os.environ.get("RAWWEBSITE_API_ENDPOINT")
    api_key: str | None = os.environ.get("RAWWEBSITE_API_KEY")

    def publish(self, post: dict, version: dict | None = None) -> dict:
        """
        Export or publish the post.

        Returns a dict with:
          - mode: publish mode used
          - slug: post slug
          - path or url: where the content was written
          - exported_at: ISO timestamp
        """
        if self.mode == "api_publish":
            return self._api_publish(post, version or {})
        return self._manual_export(post, version or {})

    def _manual_export(self, post: dict, version: dict) -> dict:
        """Write post as HTML + JSON manifest to the export directory."""
        self.export_dir.mkdir(parents=True, exist_ok=True)
        slug = post.get("slug") or post.get("id", "post")[:12]
        slug = slug.replace("/", "-").replace("\\", "-")

        html_content = self._render_html(post, version)
        json_manifest = self._build_manifest(post, version)

        html_path = self.export_dir / f"{slug}.html"
        json_path = self.export_dir / f"{slug}.json"

        html_path.write_text(html_content, encoding="utf-8")
        json_path.write_text(json.dumps(json_manifest, indent=2, ensure_ascii=False), encoding="utf-8")

        return {
            "mode": "manual_export",
            "slug": slug,
            "html_path": str(html_path),
            "json_path": str(json_path),
            "exported_at": datetime.now(timezone.utc).isoformat(),
        }

    def _api_publish(self, post: dict, version: dict) -> dict:
        """POST to rawwebsite CMS API. Requires RAWWEBSITE_API_ENDPOINT + RAWWEBSITE_API_KEY."""
        if not self.api_endpoint:
            raise NotImplementedError(
                "RAWWEBSITE_API_ENDPOINT is not configured. "
                "Set it or switch to RAWWEBSITE_PUBLISH_MODE=manual_export"
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

    def _build_manifest(self, post: dict, version: dict) -> dict:
        """Build CMS-ready JSON manifest combining post + version fields."""
        return {
            "id": post.get("id"),
            "slug": post.get("slug"),
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

    def _render_html(self, post: dict, version: dict) -> str:
        """Render a minimal HTML page for manual CMS upload."""
        title = _html.escape(version.get("seo_title") or post.get("title") or "Untitled")
        desc = _html.escape(version.get("seo_description") or post.get("seo_description") or "")
        heading = _html.escape(version.get("title") or post.get("title") or "")
        body = version.get("body_html") or post.get("body_html") or ""
        if not body:
            # Fallback: wrap markdown in <pre>
            md = _html.escape(version.get("body_markdown") or post.get("body_markdown") or "")
            body = f"<pre>{md}</pre>"
        cta_text = _html.escape(version.get("cta_text") or post.get("cta_text") or "")
        cta_url = _html.escape(version.get("cta_url") or post.get("cta_url") or "#")
        keyword = _html.escape(version.get("focus_keyword") or post.get("focus_keyword") or "")

        cta_block = (
            f'<div class="cta-block"><a href="{cta_url}" class="cta-button">{cta_text}</a></div>'
            if cta_text else ""
        )

        return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{title}</title>
  <meta name="description" content="{desc}">
  {f'<meta name="keywords" content="{keyword}">' if keyword else ""}
  <meta property="og:title" content="{title}">
  <meta property="og:description" content="{desc}">
</head>
<body>
  <article class="post-content">
    <h1>{heading}</h1>
    <div class="post-body">
      {body}
    </div>
    {cta_block}
  </article>
</body>
</html>
"""
