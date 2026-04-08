import React, { useState, useEffect } from 'react';
import { listStores, getMarketingStores, triggerMarketingSync } from '../api';

const BRAND_COLORS = {
  bakudan: { bg: 'rgba(239, 68, 68, 0.12)', color: '#ef4444', icon: 'B', label: 'Bakudan Ramen' },
  raw: { bg: 'rgba(255, 146, 43, 0.12)', color: '#ff922b', icon: 'R', label: 'Raw Sushi Bar' },
  copper: { bg: 'rgba(252, 196, 25, 0.12)', color: '#fcc419', icon: 'S', label: 'Sunright Tea Studio' },
  ift: { bg: 'rgba(108, 92, 231, 0.12)', color: '#6c5ce7', icon: 'I', label: 'Infused Tea Lounge' },
};

function formatDate(dateStr) {
  if (!dateStr) return 'Never';
  const d = new Date(dateStr.replace(' ', 'T'));
  return d.toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric', hour: '2-digit', minute: '2-digit' });
}

export default function Stores() {
  const [stores, setStores] = useState([]);
  const [marketingData, setMarketingData] = useState(null);
  const [marketingLoading, setMarketingLoading] = useState(true);
  const [syncingAll, setSyncingAll] = useState(false);
  const [syncingId, setSyncingId] = useState(null);

  useEffect(() => {
    listStores().then(setStores).catch(() => {});
    getMarketingStores()
      .then(setMarketingData)
      .catch(() => {})
      .finally(() => setMarketingLoading(false));
  }, []);

  const handleSyncAll = async () => {
    setSyncingAll(true);
    try {
      await triggerMarketingSync();
      const fresh = await getMarketingStores();
      setMarketingData(fresh);
    } catch (e) { /* ignore */ }
    setSyncingAll(false);
  };

  const handleSyncOne = async (storeId) => {
    setSyncingId(storeId);
    try {
      await triggerMarketingSync(storeId);
      const fresh = await getMarketingStores();
      setMarketingData(fresh);
    } catch (e) { /* ignore */ }
    setSyncingId(null);
  };

  const brands = [...new Set(stores.map(s => s.brand))];

  return (
    <div className="page">
      <div className="page-header">
        <h1>Stores</h1>
        <span className="text-secondary" style={{ fontSize: 13 }}>
          {stores.length} locations across {brands.length} brands
        </span>
      </div>

      <div className="stats-row" style={{ gridTemplateColumns: 'repeat(4, 1fr)' }}>
        <div className="stat-card">
          <div className="stat-label">Total Locations</div>
          <div className="stat-value accent">{stores.length}</div>
        </div>
        <div className="stat-card">
          <div className="stat-label">Brands</div>
          <div className="stat-value">{brands.length}</div>
        </div>
        <div className="stat-card">
          <div className="stat-label">Bakudan Ramen</div>
          <div className="stat-value red">{stores.filter(s => s.brand === 'bakudan').length}</div>
        </div>
        <div className="stat-card">
          <div className="stat-label">Sunright Tea</div>
          <div className="stat-value yellow">{stores.filter(s => s.brand === 'copper').length}</div>
        </div>
      </div>

      {brands.map(brand => {
        const brandStores = stores.filter(s => s.brand === brand);
        const bc = BRAND_COLORS[brand] || BRAND_COLORS.ift;
        return (
          <div key={brand} style={{ marginBottom: 24 }}>
            <div className="section-title" style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
              <span style={{
                width: 20, height: 20, borderRadius: 5,
                background: bc.bg, color: bc.color,
                display: 'flex', alignItems: 'center', justifyContent: 'center',
                fontSize: 11, fontWeight: 700,
              }}>{bc.icon}</span>
              {bc.label || brand.charAt(0).toUpperCase() + brand.slice(1)} ({brandStores.length})
            </div>

            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(300px, 1fr))', gap: 12 }}>
              {brandStores.map(s => (
                <div key={s.id} className="org-card" style={{ textAlign: 'left', padding: 18 }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 8 }}>
                    <div style={{
                      width: 36, height: 36, borderRadius: 8,
                      background: bc.bg, color: bc.color,
                      display: 'flex', alignItems: 'center', justifyContent: 'center',
                      fontSize: 14, fontWeight: 700,
                    }}>{s.id}</div>
                    <span className="badge active" style={{ fontSize: 11 }}>Active</span>
                  </div>
                  <div style={{ fontWeight: 600, fontSize: 14, marginBottom: 4 }}>{s.name}</div>
                  <div className="text-secondary" style={{ fontSize: 12 }}>{s.address}</div>
                  {s.phone && (
                    <div style={{ fontSize: 12, marginTop: 4, color: 'var(--accent)' }}>{s.phone}</div>
                  )}
                  {s.website && (
                    <div style={{ fontSize: 11, marginTop: 2 }}>
                      <a href={`https://${s.website}`} target="_blank" rel="noopener noreferrer" style={{ color: 'var(--blue)', textDecoration: 'none' }}>
                        {s.website}
                      </a>
                    </div>
                  )}
                </div>
              ))}
            </div>
          </div>
        );
      })}

      {/* Marketing Live Data */}
      <div style={{ marginTop: 32 }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
          <div className="section-title" style={{ margin: 0 }}>Marketing Live Data</div>
          <button
            className="btn btn-primary btn-sm"
            onClick={handleSyncAll}
            disabled={syncingAll || marketingLoading}
          >
            {syncingAll ? 'Syncing...' : 'Sync All'}
          </button>
        </div>

        {marketingLoading ? (
          <div className="org-card" style={{ padding: 24, textAlign: 'center' }}>
            <span className="text-secondary">Loading marketing data...</span>
          </div>
        ) : !marketingData?.stores?.length ? (
          <div className="org-card" style={{ padding: 24, textAlign: 'center' }}>
            <span className="text-secondary">No marketing store data available.</span>
          </div>
        ) : (
          <>
            {marketingData.totals && (
              <div className="stats-row" style={{ gridTemplateColumns: 'repeat(2, 1fr)', marginBottom: 16 }}>
                <div className="stat-card">
                  <div className="stat-label">Total Marketing Revenue</div>
                  <div className="stat-value accent">${marketingData.totals.revenue?.toLocaleString() ?? '---'}</div>
                </div>
                <div className="stat-card">
                  <div className="stat-label">Total Marketing Orders</div>
                  <div className="stat-value">{marketingData.totals.orders?.toLocaleString() ?? '---'}</div>
                </div>
              </div>
            )}

            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(300px, 1fr))', gap: 12 }}>
              {marketingData.stores.map(ms => (
                <div key={ms.id} className="org-card" style={{ textAlign: 'left', padding: 18 }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 8 }}>
                    <div style={{ fontWeight: 600, fontSize: 14 }}>{ms.label || ms.id}</div>
                    <button
                      className="btn btn-ghost btn-sm"
                      onClick={() => handleSyncOne(ms.id)}
                      disabled={syncingId === ms.id}
                      style={{ fontSize: 11 }}
                    >
                      {syncingId === ms.id ? 'Syncing...' : 'Sync'}
                    </button>
                  </div>
                  <div className="text-secondary" style={{ fontSize: 12, marginBottom: 8 }}>
                    Last updated: {formatDate(ms.last_updated)}
                  </div>
                  {ms.data && (
                    <div style={{ display: 'flex', gap: 16, fontSize: 13 }}>
                      {ms.data.revenue != null && (
                        <div>
                          <span className="text-secondary">Revenue: </span>
                          <span style={{ fontWeight: 600 }}>${ms.data.revenue.toLocaleString()}</span>
                        </div>
                      )}
                      {ms.data.orders != null && (
                        <div>
                          <span className="text-secondary">Orders: </span>
                          <span style={{ fontWeight: 600 }}>{ms.data.orders.toLocaleString()}</span>
                        </div>
                      )}
                    </div>
                  )}
                </div>
              ))}
            </div>
          </>
        )}
      </div>
    </div>
  );
}
