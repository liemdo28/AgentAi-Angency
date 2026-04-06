import React, { useState, useEffect } from 'react';
import { listStores } from '../api';

const BRAND_COLORS = {
  bakudan: { bg: 'rgba(239, 68, 68, 0.12)', color: '#ef4444', icon: 'B' },
  raw: { bg: 'rgba(34, 184, 207, 0.12)', color: '#22b8cf', icon: 'R' },
  copper: { bg: 'rgba(252, 196, 25, 0.12)', color: '#fcc419', icon: 'C' },
  ift: { bg: 'rgba(81, 207, 102, 0.12)', color: '#51cf66', icon: 'F' },
};

export default function Stores() {
  const [stores, setStores] = useState([]);

  useEffect(() => {
    listStores().then(setStores).catch(() => {});
  }, []);

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
          <div className="stat-label">Bakudan Locations</div>
          <div className="stat-value red">{stores.filter(s => s.brand === 'bakudan').length}</div>
        </div>
        <div className="stat-card">
          <div className="stat-label">Other Brands</div>
          <div className="stat-value blue">{stores.filter(s => s.brand !== 'bakudan').length}</div>
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
              {brand.charAt(0).toUpperCase() + brand.slice(1)} ({brandStores.length})
            </div>

            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(300px, 1fr))', gap: 12 }}>
              {brandStores.map(s => (
                <div key={s.id} className="org-card" style={{ textAlign: 'left', padding: 18 }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 8 }}>
                    <div style={{
                      width: 36, height: 36, borderRadius: 8,
                      background: bc.bg, color: bc.color,
                      display: 'flex', alignItems: 'center', justifyContent: 'center',
                      fontSize: 16, fontWeight: 700,
                    }}>{s.id}</div>
                    <span className="badge active" style={{ fontSize: 11 }}>Active</span>
                  </div>
                  <div style={{ fontWeight: 600, fontSize: 14, marginBottom: 4 }}>{s.name}</div>
                  <div className="text-secondary" style={{ fontSize: 12 }}>{s.address}</div>
                </div>
              ))}
            </div>
          </div>
        );
      })}
    </div>
  );
}
