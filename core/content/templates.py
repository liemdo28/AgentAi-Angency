"""
HTML blog post templates extracted from existing Bakudan + Raw websites.
The generator injects content into these templates.
"""

BAKUDAN_TEMPLATE = '''<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{title} - Bakudan Ramen</title>
    <meta name="description" content="{meta_description}">
    <link href="https://fonts.googleapis.com/css2?family=Bebas+Neue&family=Noto+Sans+JP:wght@300;400;700&family=Playfair+Display:wght@700&display=swap" rel="stylesheet">
    <link rel="stylesheet" href="css/styles.css">
</head>
<body>
    <a href="#main-content" class="skip-link">Skip to main content</a>
    <header class="site-header" role="banner">
        <a href="index.html" class="logo" aria-label="Bakudan Ramen - Home">
            <div class="logo-icon" aria-hidden="true">&#29190;</div>
            <span class="logo-text">BAKUDAN RAMEN</span>
        </a>
        <nav aria-label="Main navigation">
            <ul class="nav-links">
                <li><a href="index.html">Home</a></li>
                <li><a href="menu.html">Menu</a></li>
                <li><a href="locations.html">Locations</a></li>
                <li><a href="happy-hour.html">Happy Hour</a></li>
                <li><a href="about.html">Our Story</a></li>
                <li><a href="blog.html" class="active">Blog</a></li>
                <li><a href="order.html" class="nav-cta">Order Now</a></li>
            </ul>
        </nav>
        <button class="hamburger" aria-expanded="false" aria-controls="mobile-nav" aria-label="Open menu">
            <span></span><span></span><span></span>
        </button>
    </header>
    <div class="mobile-nav" id="mobile-nav" role="navigation" aria-label="Mobile navigation">
        <a href="index.html">Home</a>
        <a href="menu.html">Menu</a>
        <a href="locations.html">Locations</a>
        <a href="happy-hour.html">Happy Hour</a>
        <a href="about.html">Our Story</a>
        <a href="blog.html">Blog</a>
        <a href="order.html">Order Now</a>
    </div>

    <main id="main-content">
        <article class="blog-post">
            <header class="blog-post-header">
                <div class="section-tag">{section_tag}</div>
                <h1>{title}</h1>
                <p class="subtitle">{subtitle}</p>
                <div class="blog-post-meta">Reading time: {reading_time} minutes</div>
            </header>

            <div class="blog-post-content">
{article_body}
            </div>

            <div class="blog-post-cta">
                <h3>Ready to Experience Bakudan Ramen?</h3>
                <p>Visit any of our three San Antonio locations and taste the difference authentic craft makes.</p>
                <a href="order.html" class="btn-primary">ORDER NOW</a>
                <a href="locations.html" class="btn-secondary" style="margin-left: 1rem;">FIND A LOCATION</a>
            </div>
        </article>
    </main>

    <footer class="site-footer">
        <div class="footer-content">
            <div class="footer-section">
                <h4>Visit Us</h4>
                <p><strong>The Rim:</strong> 17619 La Cantera Pkwy UNIT 208<br>(210) 257-8080</p>
                <p><strong>Stone Oak:</strong> 22506 U.S. Hwy 281 N Ste 106<br>(210) 437-0632</p>
                <p><strong>Bandera:</strong> 11309 Bandera Rd Ste 111<br>(210) 277-7740</p>
            </div>
            <div class="footer-section">
                <h4>Explore</h4>
                <a href="menu.html">Menu</a>
                <a href="blog.html">Blog</a>
                <a href="about.html">Our Story</a>
                <a href="order.html">Order Online</a>
            </div>
        </div>
        <div class="footer-bottom">
            <p>&copy; {year} Bakudan Ramen. All Rights Reserved.</p>
        </div>
    </footer>

    <script src="js/main.js"></script>
</body>
</html>'''

RAW_TEMPLATE = '''<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <meta name="description" content="{meta_description}">
    <meta name="keywords" content="{keywords}">
    <meta name="robots" content="index, follow">
    <link rel="canonical" href="https://www.rawsushibar.com/{filename}">
    <title>{title} | Raw Sushi Bar Blog</title>

    <meta property="og:type" content="article">
    <meta property="og:url" content="https://www.rawsushibar.com/{filename}">
    <meta property="og:title" content="{title}">
    <meta property="og:description" content="{meta_description}">

    <link rel="icon" type="image/svg+xml" href="data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 32 32'%3E%3Ccircle cx='16' cy='16' r='16' fill='%231a1a1a'/%3E%3Ccircle cx='16' cy='16' r='12' fill='%23C41E3A'/%3E%3Ctext x='16' y='22' text-anchor='middle' font-family='Georgia,serif' font-weight='bold' font-size='18' fill='white'%3ER%3C/text%3E%3C/svg%3E">

    <script type="application/ld+json">
    {{
      "@context": "https://schema.org",
      "@type": "BlogPosting",
      "mainEntityOfPage": {{
        "@type": "WebPage",
        "@id": "https://www.rawsushibar.com/{filename}"
      }},
      "headline": "{title}",
      "description": "{meta_description}",
      "author": {{
        "@type": "Person",
        "name": "Raw Sushi Bar Team"
      }},
      "publisher": {{
        "@type": "Organization",
        "name": "Raw Sushi Bar",
        "logo": {{
          "@type": "ImageObject",
          "url": "https://www.rawsushibar.com/images/logo.png"
        }}
      }},
      "datePublished": "{date_published}"
    }}
    </script>

    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{ font-family: 'Georgia', 'Times New Roman', serif; color: #1a1a1a; line-height: 1.8; background: #fafafa; }}
        .nav-bar {{ background: #1a1a1a; padding: 12px 24px; display: flex; justify-content: space-between; align-items: center; }}
        .nav-bar a {{ color: #fff; text-decoration: none; font-family: Arial, sans-serif; font-size: 14px; }}
        .nav-links {{ display: flex; gap: 20px; list-style: none; }}
        .nav-links a {{ color: #ccc; }} .nav-links a:hover {{ color: #fff; }}
        .blog-header {{ text-align: center; padding: 60px 20px 40px; max-width: 800px; margin: 0 auto; }}
        .blog-category {{ display: inline-block; background: #C41E3A; color: #fff; padding: 4px 14px; border-radius: 20px; font-family: Arial, sans-serif; font-size: 12px; letter-spacing: 1px; text-transform: uppercase; margin-bottom: 16px; }}
        .blog-header h1 {{ font-size: 2.5rem; line-height: 1.2; margin-bottom: 16px; }}
        .blog-meta {{ color: #666; font-family: Arial, sans-serif; font-size: 14px; }}
        .blog-content {{ max-width: 780px; margin: 0 auto; padding: 0 20px 60px; }}
        .blog-content h2 {{ font-size: 1.6rem; margin: 40px 0 16px; color: #1a1a1a; border-bottom: 2px solid #C41E3A; padding-bottom: 8px; }}
        .blog-content h3 {{ font-size: 1.2rem; margin: 28px 0 12px; }}
        .blog-content p {{ margin-bottom: 18px; font-size: 1.05rem; }}
        .blog-content ul, .blog-content ol {{ margin: 0 0 18px 24px; }}
        .blog-content li {{ margin-bottom: 8px; }}
        .blog-content blockquote {{ border-left: 4px solid #C41E3A; padding: 16px 20px; margin: 24px 0; background: #fff5f5; font-style: italic; }}
        .highlight-box {{ background: #fff; border-left: 4px solid #C41E3A; padding: 20px; margin: 24px 0; border-radius: 0 8px 8px 0; box-shadow: 0 2px 8px rgba(0,0,0,0.05); }}
        .cta-section {{ text-align: center; padding: 50px 20px; background: #1a1a1a; color: #fff; margin-top: 40px; }}
        .cta-section h2 {{ font-size: 1.8rem; margin-bottom: 16px; }}
        .cta-section p {{ max-width: 600px; margin: 0 auto 24px; color: #ccc; font-size: 1.05rem; }}
        .cta-btn {{ display: inline-block; background: #C41E3A; color: #fff; padding: 14px 32px; border-radius: 30px; text-decoration: none; font-family: Arial, sans-serif; font-weight: bold; font-size: 16px; }}
        .cta-btn:hover {{ background: #a01830; }}
        .back-link {{ text-align: center; padding: 30px; }}
        .back-link a {{ color: #C41E3A; text-decoration: none; font-family: Arial, sans-serif; }}
        footer {{ text-align: center; padding: 30px; background: #1a1a1a; color: #888; font-family: Arial, sans-serif; font-size: 13px; }}
    </style>
</head>
<body>
    <nav class="nav-bar">
        <a href="index.html" style="font-weight:bold; font-size:18px;">Raw Sushi Bar</a>
        <ul class="nav-links">
            <li><a href="index.html">Home</a></li>
            <li><a href="index.html#menu-section">Menu</a></li>
            <li><a href="blog.html">Blog</a></li>
        </ul>
    </nav>

    <header class="blog-header">
        <div class="blog-category">{section_tag}</div>
        <h1>{title}</h1>
        <div class="blog-meta">Published {date_display} | By Raw Sushi Bar Team | {reading_time} min read</div>
    </header>

    <article class="blog-content">
{article_body}
    </article>

    <div class="cta-section">
        <h2>Experience Raw Sushi Bar</h2>
        <p>Taste the freshness that has made us Stockton's favorite sushi destination for over 20 years.</p>
        <a href="index.html" class="cta-btn">View Our Menu</a>
        <p style="margin-top:20px; font-size:14px; color:#999;">
            10742 Trinity Parkway, Suite D, Stockton, CA<br>
            (209) 954-9729
        </p>
    </div>

    <div class="back-link"><a href="index.html">&larr; Back to Home</a></div>
    <footer><p>&copy; {year} Raw Sushi Bar. All Rights Reserved.</p></footer>
</body>
</html>'''


def get_template(brand: str) -> str:
    """Return the HTML template for a brand."""
    if brand == "bakudan":
        return BAKUDAN_TEMPLATE
    elif brand == "raw":
        return RAW_TEMPLATE
    raise ValueError(f"No template for brand: {brand}")
