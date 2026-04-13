import React, { useState, useEffect, useCallback } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import {
  getPost,
  getPostLogs,
  approvePost,
  rejectPost,
  requestRevision,
  regeneratePost,
  publishPost,
} from '../api';

const STATUS_COLORS = {
  review_pending:     '#e8a020',
  approved:           '#43b581',
  rejected:           '#f04747',
  revision_requested: '#e07820',
  generating:         '#5865f2',
  published:          '#43b581',
  publish_failed:     '#f04747',
  scheduled:          '#5865f2',
  draft:              '#72767d',
  archived:           '#72767d',
};

function StatusBadge({ status }) {
  return (
    <span
      style={{
        display: 'inline-block',
        background: STATUS_COLORS[status] || '#72767d',
        color: '#fff',
        borderRadius: 4,
        padding: '2px 8px',
        fontSize: 11,
        fontWeight: 600,
        textTransform: 'uppercase',
        letterSpacing: '0.5px',
      }}
    >
      {status?.replace(/_/g, ' ')}
    </span>
  );
}

function MetaRow({ label, value, mono }) {
  if (!value && value !== 0) return null;
  return (
    <div style={{ marginBottom: 8 }}>
      <div style={{ fontSize: 11, color: 'var(--text-dim)', textTransform: 'uppercase', letterSpacing: '0.5px', marginBottom: 2 }}>
        {label}
      </div>
      <div style={{ fontSize: 13, fontFamily: mono ? 'monospace' : undefined, wordBreak: 'break-word' }}>
        {value}
      </div>
    </div>
  );
}

function SeoSnippet({ seoTitle, seoDescription, slug }) {
  return (
    <div
      style={{
        border: '1px solid var(--border)',
        borderRadius: 6,
        padding: '10px 14px',
        background: 'var(--bg-surface)',
        maxWidth: 540,
        margin: '12px 0',
      }}
    >
      <div style={{ fontSize: 11, color: 'var(--text-dim)', marginBottom: 4 }}>Google preview</div>
      <div style={{ color: '#1a0dab', fontSize: 16, fontWeight: 400, marginBottom: 2, lineHeight: 1.3 }}>
        {seoTitle || 'No SEO title set'}
      </div>
      <div style={{ color: '#006621', fontSize: 12, marginBottom: 4 }}>
        rawwebsite.com/{slug || '…'}
      </div>
      <div style={{ color: '#545454', fontSize: 13, lineHeight: 1.4 }}>
        {seoDescription || 'No meta description set.'}
      </div>
    </div>
  );
}

function AuditTimeline({ logs }) {
  if (!logs?.length) return <div style={{ color: 'var(--text-dim)', fontSize: 12 }}>No actions recorded yet.</div>;
  return (
    <div className="trace-list">
      {logs.map((entry, i) => {
        const isPositive = ['approve', 'publish', 'post_approved', 'post_generated', 'post_published'].includes(entry.action_type);
        const isNegative = ['reject', 'post_rejected', 'post_publish_failed'].includes(entry.action_type);
        const dotColor = isPositive ? '#43b581' : isNegative ? '#f04747' : 'var(--text-dim)';
        return (
          <div key={entry.id || i} className="trace-item">
            <div className="trace-dot" style={{ background: dotColor }} />
            <div style={{ flex: 1, minWidth: 0 }}>
              <div style={{ fontSize: 12, fontWeight: 600 }}>
                {entry.action_type?.replace(/_/g, ' ')}
              </div>
              <div style={{ fontSize: 11, color: 'var(--text-dim)' }}>
                {entry.actor}
                {entry.actor_type && entry.actor_type !== 'human_reviewer' && ` (${entry.actor_type})`}
              </div>
              {entry.comment && (
                <div style={{ fontSize: 11, color: 'var(--text-dim)', marginTop: 2, fontStyle: 'italic' }}>
                  "{entry.comment}"
                </div>
              )}
              <div style={{ fontSize: 10, color: 'var(--text-dim)', marginTop: 2 }}>
                {entry.from_status && entry.to_status
                  ? `${entry.from_status} → ${entry.to_status}`
                  : entry.to_status}
              </div>
              <div style={{ fontSize: 10, color: 'var(--text-dim)' }}>
                {entry.created_at ? new Date(entry.created_at).toLocaleString() : ''}
              </div>
            </div>
          </div>
        );
      })}
    </div>
  );
}

export default function PostPreview() {
  const { id } = useParams();
  const navigate = useNavigate();

  const [post, setPost] = useState(null);
  const [versions, setVersions] = useState([]);
  const [logs, setLogs] = useState([]);
  const [selectedVersionId, setSelectedVersionId] = useState(null);
  const [activeTab, setActiveTab] = useState('markdown'); // markdown | seo
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  // Review action state
  const [reviewer, setReviewer] = useState('operator');
  const [reviewComment, setReviewComment] = useState('');
  const [actionLoading, setActionLoading] = useState(false);
  const [actionError, setActionError] = useState(null);

  const load = useCallback(() => {
    setLoading(true);
    setError(null);
    Promise.all([getPost(id), getPostLogs(id)])
      .then(([postData, logData]) => {
        setPost(postData.post || postData);
        const vers = postData.versions || [];
        setVersions(vers);
        if (vers.length > 0 && !selectedVersionId) {
          setSelectedVersionId(vers[vers.length - 1].id);
        }
        setLogs(logData.logs || []);
      })
      .catch((e) => setError(e.message || 'Failed to load post'))
      .finally(() => setLoading(false));
  }, [id]);

  useEffect(() => {
    load();
  }, [load]);

  const selectedVersion = versions.find((v) => v.id === selectedVersionId) || versions[versions.length - 1] || null;

  const doAction = async (fn) => {
    setActionLoading(true);
    setActionError(null);
    try {
      await fn();
      setReviewComment('');
      await load();
    } catch (e) {
      setActionError(e.message || 'Action failed');
    } finally {
      setActionLoading(false);
    }
  };

  if (loading) {
    return (
      <div className="page" style={{ textAlign: 'center', padding: 60, color: 'var(--text-dim)' }}>
        Loading post…
      </div>
    );
  }
  if (error) {
    return (
      <div className="page">
        <div style={{ color: '#f04747', padding: 24 }}>{error}</div>
        <button className="btn btn-ghost btn-sm" onClick={() => navigate('/posts')}>
          ← Back to queue
        </button>
      </div>
    );
  }
  if (!post) return null;

  const status = post.status;
  const canApprove = status === 'review_pending';
  const canReject = status === 'review_pending';
  const canRevise = status === 'review_pending';
  const canPublish = status === 'approved' || status === 'scheduled';
  const canRegenerate = status === 'revision_requested' || status === 'review_pending';

  return (
    <div className="page" style={{ padding: 0 }}>
      {/* Top bar */}
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          gap: 12,
          padding: '12px 24px',
          borderBottom: '1px solid var(--border)',
          background: 'var(--bg-surface)',
        }}
      >
        <button className="btn btn-ghost btn-sm" onClick={() => navigate('/posts')}>
          ← Posts
        </button>
        <div style={{ flex: 1, fontWeight: 600, fontSize: 14, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
          {post.title || '(untitled)'}
        </div>
        <StatusBadge status={status} />
      </div>

      {/* 3-column layout */}
      <div
        style={{
          display: 'grid',
          gridTemplateColumns: '260px 1fr 300px',
          height: 'calc(100vh - 120px)',
          overflow: 'hidden',
        }}
      >
        {/* ── Left: metadata + SEO ──────────────────────────── */}
        <div
          style={{
            borderRight: '1px solid var(--border)',
            padding: 20,
            overflowY: 'auto',
          }}
        >
          <div style={{ fontSize: 11, fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.7px', color: 'var(--text-dim)', marginBottom: 16 }}>
            Metadata
          </div>

          <MetaRow label="Brand" value={post.brand_name} />
          <MetaRow label="Channel" value={post.channel} />
          <MetaRow label="Post Type" value={post.post_type} />
          <MetaRow label="Target Audience" value={post.target_audience} />
          <MetaRow label="Campaign" value={post.campaign_id} />
          <MetaRow label="Created by" value={post.created_by} />
          {post.approved_by && <MetaRow label="Approved by" value={post.approved_by} />}
          <MetaRow
            label="Created"
            value={post.created_at ? new Date(post.created_at).toLocaleString() : null}
          />
          {post.scheduled_for && (
            <MetaRow label="Scheduled for" value={new Date(post.scheduled_for).toLocaleString()} />
          )}
          {post.published_at && (
            <MetaRow label="Published at" value={new Date(post.published_at).toLocaleString()} />
          )}

          <div
            style={{
              borderTop: '1px solid var(--border)',
              marginTop: 16,
              paddingTop: 16,
            }}
          >
            <div style={{ fontSize: 11, fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.7px', color: 'var(--text-dim)', marginBottom: 12 }}>
              SEO
            </div>
            <MetaRow label="SEO Title" value={selectedVersion?.seo_title || post.seo_title} />
            <MetaRow label="SEO Description" value={selectedVersion?.seo_description || post.seo_description} />
            <MetaRow label="Focus Keyword" value={selectedVersion?.focus_keyword || post.focus_keyword} />
            <MetaRow label="Slug" value={post.slug} mono />
          </div>

          {(selectedVersion?.cta_text || post.cta_text) && (
            <div style={{ borderTop: '1px solid var(--border)', marginTop: 16, paddingTop: 16 }}>
              <div style={{ fontSize: 11, fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.7px', color: 'var(--text-dim)', marginBottom: 12 }}>
                CTA
              </div>
              <MetaRow label="Button Text" value={selectedVersion?.cta_text || post.cta_text} />
              <MetaRow label="CTA URL" value={selectedVersion?.cta_url || post.cta_url} mono />
            </div>
          )}

          {selectedVersion?.agent_score != null && (
            <div style={{ borderTop: '1px solid var(--border)', marginTop: 16, paddingTop: 16 }}>
              <div style={{ fontSize: 11, color: 'var(--text-dim)', marginBottom: 4 }}>Agent score</div>
              <div style={{ fontSize: 22, fontWeight: 700 }}>
                {selectedVersion.agent_score.toFixed(1)}
                <span style={{ fontSize: 13, fontWeight: 400, color: 'var(--text-dim)' }}>/100</span>
              </div>
            </div>
          )}
        </div>

        {/* ── Center: content preview ────────────────────────── */}
        <div style={{ display: 'flex', flexDirection: 'column', overflow: 'hidden' }}>
          {/* Version selector + tabs */}
          <div
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: 12,
              padding: '10px 20px',
              borderBottom: '1px solid var(--border)',
              background: 'var(--bg-surface)',
              flexShrink: 0,
            }}
          >
            {versions.length > 1 && (
              <select
                className="input"
                style={{ width: 'auto', padding: '4px 8px', fontSize: 13 }}
                value={selectedVersionId || ''}
                onChange={(e) => setSelectedVersionId(e.target.value)}
              >
                {versions.map((v) => (
                  <option key={v.id} value={v.id}>
                    Version {v.version_no}
                    {v.agent_score != null ? ` — ${v.agent_score.toFixed(0)} pts` : ''}
                  </option>
                ))}
              </select>
            )}
            {versions.length === 1 && (
              <span style={{ fontSize: 13, color: 'var(--text-dim)' }}>Version 1</span>
            )}
            <div style={{ display: 'flex', gap: 4, marginLeft: 'auto' }}>
              {['markdown', 'seo'].map((tab) => (
                <button
                  key={tab}
                  className={`tab-btn${activeTab === tab ? ' active' : ''}`}
                  style={{ padding: '4px 12px', fontSize: 12 }}
                  onClick={() => setActiveTab(tab)}
                >
                  {tab === 'markdown' ? 'Content' : 'SEO Preview'}
                </button>
              ))}
            </div>
          </div>

          {/* Content area */}
          <div style={{ flex: 1, overflowY: 'auto', padding: 24 }}>
            {activeTab === 'markdown' && (
              <>
                {selectedVersion?.title && (
                  <h2 style={{ marginTop: 0, marginBottom: 12, fontSize: 20 }}>{selectedVersion.title}</h2>
                )}
                {selectedVersion?.excerpt && (
                  <p style={{ color: 'var(--text-dim)', fontSize: 14, fontStyle: 'italic', marginBottom: 20 }}>
                    {selectedVersion.excerpt}
                  </p>
                )}
                {selectedVersion?.body_markdown ? (
                  <pre
                    style={{
                      fontFamily: 'var(--font-mono, monospace)',
                      fontSize: 13,
                      lineHeight: 1.7,
                      whiteSpace: 'pre-wrap',
                      wordBreak: 'break-word',
                      background: 'var(--bg-base)',
                      border: '1px solid var(--border)',
                      borderRadius: 6,
                      padding: 16,
                      margin: 0,
                    }}
                  >
                    {selectedVersion.body_markdown}
                  </pre>
                ) : (
                  <div style={{ color: 'var(--text-dim)', padding: 24, textAlign: 'center' }}>
                    No content generated yet.
                  </div>
                )}
                {(selectedVersion?.cta_text) && (
                  <div
                    style={{
                      marginTop: 24,
                      padding: 16,
                      background: 'var(--bg-surface)',
                      border: '1px solid var(--border)',
                      borderRadius: 6,
                    }}
                  >
                    <div style={{ fontSize: 11, color: 'var(--text-dim)', marginBottom: 8, textTransform: 'uppercase' }}>
                      CTA Preview
                    </div>
                    <a
                      href={selectedVersion.cta_url || '#'}
                      target="_blank"
                      rel="noreferrer"
                      style={{
                        display: 'inline-block',
                        background: 'var(--accent)',
                        color: '#fff',
                        padding: '8px 20px',
                        borderRadius: 4,
                        textDecoration: 'none',
                        fontWeight: 600,
                        fontSize: 14,
                      }}
                    >
                      {selectedVersion.cta_text}
                    </a>
                  </div>
                )}
              </>
            )}

            {activeTab === 'seo' && (
              <>
                <div style={{ fontSize: 13, color: 'var(--text-dim)', marginBottom: 12 }}>
                  How this post may appear in Google search results:
                </div>
                <SeoSnippet
                  seoTitle={selectedVersion?.seo_title || post.seo_title}
                  seoDescription={selectedVersion?.seo_description || post.seo_description}
                  slug={post.slug}
                />
                {selectedVersion?.featured_image_prompt && (
                  <div style={{ marginTop: 24 }}>
                    <div style={{ fontSize: 11, color: 'var(--text-dim)', textTransform: 'uppercase', letterSpacing: '0.5px', marginBottom: 8 }}>
                      Featured Image Prompt (for AI image generation)
                    </div>
                    <div
                      style={{
                        background: 'var(--bg-base)',
                        border: '1px solid var(--border)',
                        borderRadius: 6,
                        padding: 12,
                        fontSize: 13,
                        fontStyle: 'italic',
                        color: 'var(--text-dim)',
                      }}
                    >
                      {selectedVersion.featured_image_prompt}
                    </div>
                  </div>
                )}
              </>
            )}
          </div>
        </div>

        {/* ── Right: review actions + timeline ──────────────── */}
        <div
          style={{
            borderLeft: '1px solid var(--border)',
            display: 'flex',
            flexDirection: 'column',
            overflow: 'hidden',
          }}
        >
          {/* Actions panel */}
          <div style={{ padding: 20, borderBottom: '1px solid var(--border)', flexShrink: 0 }}>
            <div style={{ fontSize: 11, fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.7px', color: 'var(--text-dim)', marginBottom: 12 }}>
              Review Actions
            </div>

            <div style={{ marginBottom: 10 }}>
              <label style={{ fontSize: 11, color: 'var(--text-dim)', display: 'block', marginBottom: 4 }}>
                Reviewer
              </label>
              <input
                className="input"
                style={{ width: '100%', boxSizing: 'border-box' }}
                value={reviewer}
                onChange={(e) => setReviewer(e.target.value)}
                placeholder="Your name"
              />
            </div>

            <div style={{ marginBottom: 12 }}>
              <label style={{ fontSize: 11, color: 'var(--text-dim)', display: 'block', marginBottom: 4 }}>
                Comment / Feedback
              </label>
              <textarea
                className="input"
                rows={3}
                style={{ width: '100%', boxSizing: 'border-box', resize: 'vertical' }}
                value={reviewComment}
                onChange={(e) => setReviewComment(e.target.value)}
                placeholder="Optional note or feedback…"
              />
            </div>

            {actionError && (
              <div style={{ color: '#f04747', fontSize: 12, marginBottom: 8 }}>{actionError}</div>
            )}

            <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
              {canApprove && (
                <button
                  className="btn btn-sm"
                  style={{ background: '#43b581', color: '#fff', border: 'none', width: '100%' }}
                  disabled={actionLoading || !reviewer.trim()}
                  onClick={() =>
                    doAction(() => approvePost(id, { reviewer, comment: reviewComment }))
                  }
                >
                  Approve
                </button>
              )}
              {canReject && (
                <button
                  className="btn btn-sm"
                  style={{ background: '#f04747', color: '#fff', border: 'none', width: '100%' }}
                  disabled={actionLoading || !reviewer.trim() || !reviewComment.trim()}
                  onClick={() =>
                    doAction(() => rejectPost(id, { reviewer, reason: reviewComment }))
                  }
                >
                  Reject
                </button>
              )}
              {canRevise && (
                <button
                  className="btn btn-ghost btn-sm"
                  style={{ width: '100%' }}
                  disabled={actionLoading || !reviewer.trim() || !reviewComment.trim()}
                  onClick={() =>
                    doAction(() => requestRevision(id, { reviewer, feedback: reviewComment }))
                  }
                >
                  Request Revision
                </button>
              )}
              {canRegenerate && (
                <button
                  className="btn btn-ghost btn-sm"
                  style={{ width: '100%' }}
                  disabled={actionLoading || !reviewComment.trim()}
                  onClick={() =>
                    doAction(() => regeneratePost(id, { feedback: reviewComment }))
                  }
                >
                  Regenerate
                </button>
              )}
              {canPublish && (
                <button
                  className="btn btn-sm"
                  style={{ background: '#5865f2', color: '#fff', border: 'none', width: '100%' }}
                  disabled={actionLoading}
                  onClick={() => doAction(() => publishPost(id))}
                >
                  Publish
                </button>
              )}
            </div>
          </div>

          {/* Audit timeline */}
          <div style={{ flex: 1, overflowY: 'auto', padding: 20 }}>
            <div style={{ fontSize: 11, fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.7px', color: 'var(--text-dim)', marginBottom: 12 }}>
              Audit Timeline
            </div>
            <AuditTimeline logs={logs} />
          </div>
        </div>
      </div>
    </div>
  );
}
