"""SQL schema for post review & approval tables."""

POSTS_SCHEMA = """
-- POSTS -----------------------------------------------------------------------
-- Master post record. One post can have many versions.
CREATE TABLE IF NOT EXISTS posts (
    id TEXT PRIMARY KEY,
    account_id TEXT,
    brand_name TEXT DEFAULT 'Raw Sushi Bar',
    channel TEXT DEFAULT 'rawwebsite',
    title TEXT,
    slug TEXT,
    excerpt TEXT,
    body_markdown TEXT,
    body_html TEXT,
    cta_text TEXT,
    cta_url TEXT,
    target_audience TEXT,
    campaign_id TEXT,
    post_type TEXT,
    -- State machine: draft → generating → review_pending → approved/rejected/revision_requested
    --                → scheduled → published / publish_failed / archived
    status TEXT DEFAULT 'draft',
    seo_title TEXT,
    seo_description TEXT,
    focus_keyword TEXT,
    og_image_url TEXT,
    featured_image_url TEXT,
    scheduled_for TEXT,
    published_at TEXT,
    created_by TEXT DEFAULT 'ai_agent',
    approved_by TEXT,
    created_at TEXT DEFAULT (datetime('now')),
    updated_at TEXT DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_posts_status ON posts(status, channel);
CREATE INDEX IF NOT EXISTS idx_posts_brand ON posts(brand_name, channel);
CREATE INDEX IF NOT EXISTS idx_posts_campaign ON posts(campaign_id);

-- POST VERSIONS ----------------------------------------------------------------
-- Immutable snapshots of generated content. Each generation cycle creates a
-- new version; old versions remain read-only for audit purposes.
CREATE TABLE IF NOT EXISTS post_versions (
    id TEXT PRIMARY KEY,
    post_id TEXT NOT NULL REFERENCES posts(id),
    version_no INTEGER NOT NULL,
    generation_prompt TEXT,
    model_provider TEXT DEFAULT 'anthropic',
    model_name TEXT,
    title TEXT,
    excerpt TEXT,
    body_markdown TEXT,
    body_html TEXT,
    cta_text TEXT,
    cta_url TEXT,
    seo_title TEXT,
    seo_description TEXT,
    focus_keyword TEXT,
    featured_image_prompt TEXT,
    featured_image_url TEXT,
    agent_score REAL DEFAULT 0.0,
    -- Version-level review state: pending / approved / rejected
    review_status TEXT DEFAULT 'pending',
    review_notes TEXT,
    created_at TEXT DEFAULT (datetime('now')),
    UNIQUE(post_id, version_no)
);
CREATE INDEX IF NOT EXISTS idx_post_versions_post ON post_versions(post_id, version_no);

-- POST REVIEW ACTIONS ---------------------------------------------------------
-- Every approve / reject / request-revision / publish / archive action.
-- This is the authoritative per-post audit trail.
CREATE TABLE IF NOT EXISTS post_review_actions (
    id TEXT PRIMARY KEY,
    post_id TEXT NOT NULL REFERENCES posts(id),
    post_version_id TEXT REFERENCES post_versions(id),
    actor TEXT NOT NULL,
    -- ai_agent | human_reviewer | system
    actor_type TEXT DEFAULT 'human_reviewer',
    -- generate / submit_review / approve / reject / request_revision /
    -- regenerate / publish / archive / post_generate_started / post_generated /
    -- review_opened / post_scheduled / post_publish_started / post_published /
    -- post_publish_failed / post_archived
    action_type TEXT NOT NULL,
    from_status TEXT,
    to_status TEXT,
    comment TEXT,
    payload_json TEXT DEFAULT '{}',
    created_at TEXT DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_post_actions_post ON post_review_actions(post_id, created_at);
CREATE INDEX IF NOT EXISTS idx_post_actions_type ON post_review_actions(action_type, created_at);
"""
