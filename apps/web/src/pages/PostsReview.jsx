import React, { useState, useEffect, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  listReviewQueue,
  approvePost,
  rejectPost,
  requestRevision,
} from '../api';

const STATUS_TABS = [
  { value: 'review_pending', label: 'Pending Review' },
  { value: 'approved',       label: 'Approved' },
  { value: 'rejected',       label: 'Rejected' },
  { value: 'revision_requested', label: 'Revision Requested' },
  { value: 'published',      label: 'Published' },
  { value: 'all',            label: 'All' },
];

const POST_TYPE_LABELS = {
  promo:           'Promo',
  event:           'Event',
  blog:            'Blog',
  seasonal:        'Seasonal',
  'landing-content': 'Landing',
};

const STATUS_COLORS = {
  review_pending:      'var(--yellow, #e8a020)',
  approved:            'var(--green, #43b581)',
  rejected:            'var(--red, #f04747)',
  revision_requested:  'var(--orange, #e07820)',
  generating:          'var(--blue, #5865f2)',
  published:           'var(--green, #43b581)',
  publish_failed:      'var(--red, #f04747)',
  scheduled:           'var(--blue, #5865f2)',
  draft:               'var(--text-dim, #72767d)',
  archived:            'var(--text-dim, #72767d)',
};

function StatusBadge({ status }) {
  return (
    <span
      style={{
        background: STATUS_COLORS[status] || 'var(--text-dim, #72767d)',
        color: '#fff',
        borderRadius: 4,
        padding: '2px 8px',
        fontSize: 11,
        fontWeight: 600,
        whiteSpace: 'nowrap',
        textTransform: 'uppercase',
        letterSpacing: '0.5px',
      }}
    >
      {status?.replace(/_/g, ' ')}
    </span>
  );
}

function ScoreBar({ score }) {
  if (score == null) return null;
  const pct = Math.max(0, Math.min(100, score));
  const color = pct >= 80 ? '#43b581' : pct >= 50 ? '#e8a020' : '#f04747';
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
      <div
        style={{
          flex: 1,
          height: 4,
          background: 'var(--bg-base, #2c2f33)',
          borderRadius: 2,
          overflow: 'hidden',
        }}
      >
        <div style={{ width: `${pct}%`, height: '100%', background: color, borderRadius: 2 }} />
      </div>
      <span style={{ fontSize: 11, color: 'var(--text-dim)', whiteSpace: 'nowrap' }}>
        {pct.toFixed(0)}
      </span>
    </div>
  );
}

function ActionModal({ action, onClose, onConfirm }) {
  const [comment, setComment] = useState('');
  if (!action) return null;

  const titles = {
    approve:          'Approve Post',
    reject:           'Reject Post',
    request_revision: 'Request Revision',
  };
  const placeholders = {
    approve:          'Optional comment for the record…',
    reject:           'Reason for rejection (required)…',
    request_revision: 'Describe what needs to change…',
  };
  const btnLabels = { approve: 'Approve', reject: 'Reject', request_revision: 'Send Feedback' };
  const btnColors = {
    approve:          '#43b581',
    reject:           '#f04747',
    request_revision: '#e07820',
  };

  return (
    <div
      style={{
        position: 'fixed',
        inset: 0,
        background: 'rgba(0,0,0,0.6)',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        zIndex: 1000,
      }}
      onClick={onClose}
    >
      <div
        className="card"
        style={{ padding: 24, minWidth: 360, maxWidth: 480, width: '90%' }}
        onClick={(e) => e.stopPropagation()}
      >
        <div style={{ fontWeight: 700, fontSize: 15, marginBottom: 12 }}>
          {titles[action.type]}
        </div>
        <div style={{ fontSize: 12, color: 'var(--text-dim)', marginBottom: 12 }}>
          {action.title}
        </div>
        <textarea
          className="input"
          rows={4}
          style={{ width: '100%', marginBottom: 16, resize: 'vertical', boxSizing: 'border-box' }}
          placeholder={placeholders[action.type]}
          value={comment}
          onChange={(e) => setComment(e.target.value)}
          autoFocus
        />
        <div style={{ display: 'flex', gap: 8, justifyContent: 'flex-end' }}>
          <button className="btn btn-ghost btn-sm" onClick={onClose}>
            Cancel
          </button>
          <button
            className="btn btn-sm"
            style={{ background: btnColors[action.type], color: '#fff', border: 'none' }}
            onClick={() => onConfirm(comment)}
            disabled={action.type === 'reject' && !comment.trim()}
          >
            {btnLabels[action.type]}
          </button>
        </div>
      </div>
    </div>
  );
}

export default function PostsReview() {
  const navigate = useNavigate();
  const [posts, setPosts] = useState([]);
  const [filter, setFilter] = useState('review_pending');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [activeModal, setActiveModal] = useState(null); // { type, postId, title }

  const load = useCallback(() => {
    setLoading(true);
    setError(null);
    listReviewQueue({ status: filter === 'all' ? undefined : filter })
      .then((r) => setPosts(r.posts || []))
      .catch((e) => setError(e.message || 'Failed to load posts'))
      .finally(() => setLoading(false));
  }, [filter]);

  useEffect(() => {
    load();
  }, [load]);

  const handleModalConfirm = async (comment) => {
    if (!activeModal) return;
    const { type, postId } = activeModal;
    try {
      if (type === 'approve') {
        await approvePost(postId, { reviewer: 'operator', comment: comment || '' });
      } else if (type === 'reject') {
        await rejectPost(postId, { reviewer: 'operator', reason: comment });
      } else if (type === 'request_revision') {
        await requestRevision(postId, { reviewer: 'operator', feedback: comment });
      }
    } catch (e) {
      console.error('Action failed:', e);
    }
    setActiveModal(null);
    load();
  };

  return (
    <div className="page">
      {/* Filter tabs */}
      <div className="tab-bar" style={{ marginBottom: 20 }}>
        {STATUS_TABS.map((tab) => (
          <button
            key={tab.value}
            className={`tab-btn${filter === tab.value ? ' active' : ''}`}
            onClick={() => setFilter(tab.value)}
          >
            {tab.label}
          </button>
        ))}
      </div>

      {/* Error */}
      {error && (
        <div
          style={{
            background: 'rgba(240,71,71,0.1)',
            border: '1px solid #f04747',
            borderRadius: 6,
            padding: '10px 14px',
            marginBottom: 16,
            color: '#f04747',
            fontSize: 13,
          }}
        >
          {error}
          <button
            style={{ marginLeft: 12, fontSize: 12, color: '#f04747', textDecoration: 'underline', cursor: 'pointer', background: 'none', border: 'none' }}
            onClick={load}
          >
            Retry
          </button>
        </div>
      )}

      {/* Loading */}
      {loading && (
        <div style={{ textAlign: 'center', padding: 40, color: 'var(--text-dim)' }}>
          Loading posts…
        </div>
      )}

      {/* Empty state */}
      {!loading && !error && posts.length === 0 && (
        <div
          className="empty-state"
          style={{
            background: 'var(--bg-surface)',
            border: '1px solid var(--border)',
            borderRadius: 'var(--radius-lg)',
            padding: 48,
            textAlign: 'center',
          }}
        >
          <div style={{ fontSize: 32, marginBottom: 12 }}>~</div>
          <div style={{ color: 'var(--text-dim)' }}>
            No posts in <strong>{filter === 'all' ? 'any status' : filter.replace(/_/g, ' ')}</strong>
          </div>
        </div>
      )}

      {/* Post cards */}
      {!loading &&
        posts.map((post) => (
          <div className="approval-card" key={post.id} style={{ marginBottom: 12 }}>
            <div className="approval-header">
              <div style={{ flex: 1, minWidth: 0 }}>
                {/* Title row */}
                <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap', marginBottom: 4 }}>
                  <span
                    style={{ fontWeight: 600, fontSize: 14, cursor: 'pointer', color: 'var(--accent)' }}
                    onClick={() => navigate(`/posts/${post.id}`)}
                    title="Open preview"
                  >
                    {post.title || '(untitled)'}
                  </span>
                  <StatusBadge status={post.status} />
                  {post.post_type && (
                    <span
                      style={{
                        background: 'var(--bg-base)',
                        border: '1px solid var(--border)',
                        borderRadius: 4,
                        padding: '1px 7px',
                        fontSize: 11,
                        color: 'var(--text-dim)',
                      }}
                    >
                      {POST_TYPE_LABELS[post.post_type] || post.post_type}
                    </span>
                  )}
                  {post.version_no != null && (
                    <span style={{ fontSize: 11, color: 'var(--text-dim)' }}>
                      v{post.version_no}
                    </span>
                  )}
                </div>

                {/* Excerpt */}
                {post.excerpt && (
                  <div
                    style={{
                      fontSize: 12,
                      color: 'var(--text-dim)',
                      marginBottom: 6,
                      overflow: 'hidden',
                      textOverflow: 'ellipsis',
                      whiteSpace: 'nowrap',
                      maxWidth: '100%',
                    }}
                  >
                    {post.excerpt}
                  </div>
                )}

                {/* Meta row */}
                <div style={{ display: 'flex', gap: 12, alignItems: 'center', flexWrap: 'wrap' }}>
                  <span style={{ fontSize: 11, color: 'var(--text-dim)' }}>
                    {post.channel || 'rawwebsite'}
                  </span>
                  {post.brand_name && (
                    <span style={{ fontSize: 11, color: 'var(--text-dim)' }}>
                      {post.brand_name}
                    </span>
                  )}
                  {post.created_at && (
                    <span style={{ fontSize: 11, color: 'var(--text-dim)' }}>
                      {new Date(post.created_at).toLocaleDateString()}
                    </span>
                  )}
                  {post.agent_score != null && (
                    <div style={{ width: 80 }}>
                      <ScoreBar score={post.agent_score} />
                    </div>
                  )}
                </div>
              </div>

              {/* Action buttons */}
              <div
                style={{ display: 'flex', gap: 6, flexShrink: 0, flexWrap: 'wrap', alignItems: 'flex-start' }}
              >
                <button
                  className="btn btn-ghost btn-sm"
                  onClick={() => navigate(`/posts/${post.id}`)}
                >
                  Preview
                </button>
                {post.status === 'review_pending' && (
                  <>
                    <button
                      className="btn btn-sm"
                      style={{ background: '#43b581', color: '#fff', border: 'none' }}
                      onClick={() =>
                        setActiveModal({ type: 'approve', postId: post.id, title: post.title })
                      }
                    >
                      Approve
                    </button>
                    <button
                      className="btn btn-sm"
                      style={{ background: '#f04747', color: '#fff', border: 'none' }}
                      onClick={() =>
                        setActiveModal({ type: 'reject', postId: post.id, title: post.title })
                      }
                    >
                      Reject
                    </button>
                    <button
                      className="btn btn-ghost btn-sm"
                      onClick={() =>
                        setActiveModal({ type: 'request_revision', postId: post.id, title: post.title })
                      }
                    >
                      Revise
                    </button>
                  </>
                )}
              </div>
            </div>
          </div>
        ))}

      {/* Action modal */}
      <ActionModal
        action={activeModal}
        onClose={() => setActiveModal(null)}
        onConfirm={handleModalConfirm}
      />
    </div>
  );
}
