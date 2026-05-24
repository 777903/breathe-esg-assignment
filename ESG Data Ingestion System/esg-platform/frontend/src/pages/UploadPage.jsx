/**
 * UploadPage — file ingestion interface.
 *
 * Layout:
 *   Left:  Upload form (data source selector + drop zone)
 *   Right: Instructions and sample data guidance
 */

import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import UploadForm from '../components/UploadForm';
import { fetchDataSources, seedDemoData } from '../services/api';

export default function UploadPage() {
  const [dataSources, setDataSources] = useState([]);
  const [loadingDS, setLoadingDS] = useState(true);
  const [seedError, setSeedError] = useState(null);
  const navigate = useNavigate();

  useEffect(() => {
    loadDataSources();
  }, []);

  async function loadDataSources() {
    setLoadingDS(true);
    try {
      const sources = await fetchDataSources();
      setDataSources(sources);
    } catch (_) {
      // May fail if backend isn't seeded yet — try seeding
    } finally {
      setLoadingDS(false);
    }
  }

  async function handleSeed() {
    setSeedError(null);
    try {
      await seedDemoData();
      await loadDataSources();
    } catch (err) {
      setSeedError(err.message);
    }
  }

  function handleUploadSuccess(summary) {
    // Navigate to dashboard after short delay
    setTimeout(() => navigate('/dashboard'), 1500);
  }

  return (
    <div className="fade-in-up">
      {/* Page header */}
      <div className="section-header mb-6">
        <div className="section-title">
          <span className="section-icon">⬆️</span>
          <div>
            <h1>Data Ingestion</h1>
            <p style={{ marginTop: 4 }}>
              Upload SAP, Utility, or Travel CSV exports for processing
            </p>
          </div>
        </div>
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: '1.5fr 1fr', gap: 'var(--space-6)' }}>
        {/* Left: Upload form */}
        <div className="card">
          <div className="card-header">
            <h3 className="card-title">Upload File</h3>
            {dataSources.length === 0 && !loadingDS && (
              <button
                id="btn-seed-demo"
                className="btn btn-ghost btn-sm"
                onClick={handleSeed}
              >
                ⚡ Setup Demo Data
              </button>
            )}
          </div>

          {seedError && (
            <div className="alert alert-error mb-4">{seedError}</div>
          )}

          {loadingDS ? (
            <div className="loading-center" style={{ padding: 'var(--space-8)' }}>
              <div className="spinner" />
              <p>Loading data sources...</p>
            </div>
          ) : (
            <UploadForm
              dataSources={dataSources}
              onUploadSuccess={handleUploadSuccess}
            />
          )}
        </div>

        {/* Right: Instructions */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-5)' }}>
          <div className="card">
            <h3 className="card-title mb-4">Supported Sources</h3>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-4)' }}>
              <SourceInfo
                icon="🏭"
                name="SAP (Fuel & Procurement)"
                color="var(--scope1)"
                details={[
                  'Standard SAP ECC export format',
                  'Handles European decimal notation',
                  'Flexible column name matching',
                  'Units: L, LTR, M3, Gal, Kg...',
                ]}
              />
              <SourceInfo
                icon="⚡"
                name="Utility (Electricity)"
                color="var(--scope2)"
                details={[
                  'Billing periods (non-calendar months)',
                  'kWh and MWh auto-conversion',
                  'Estimated read flagging',
                  'Multi-meter support',
                ]}
              />
              <SourceInfo
                icon="✈️"
                name="Corporate Travel"
                color="var(--scope3)"
                details={[
                  'IATA airport code → distance',
                  'Flight class emission factors',
                  'Hotel night-based emissions',
                  'Miles ↔ km conversion',
                ]}
              />
            </div>
          </div>

          <div className="card">
            <h3 className="card-title mb-4">📁 Sample Data Files</h3>
            <p style={{ fontSize: '0.85rem', marginBottom: 'var(--space-3)' }}>
              Find realistic sample CSVs in <span className="mono">backend/sample_data/</span>
            </p>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
              {[
                { file: 'sap_fuel_export.csv', desc: '15 rows, mixed units, edge cases' },
                { file: 'utility_electricity.csv', desc: '12 rows, multi-site billing periods' },
                { file: 'corporate_travel.csv', desc: '24 rows, IATA codes, mixed modes' },
              ].map(s => (
                <div key={s.file} style={{ padding: '8px 12px', background: 'var(--bg-elevated)', borderRadius: 'var(--radius-sm)' }}>
                  <div className="mono" style={{ fontSize: '0.8rem', color: 'var(--accent-blue-lt)' }}>{s.file}</div>
                  <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)', marginTop: 2 }}>{s.desc}</div>
                </div>
              ))}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

function SourceInfo({ icon, name, color, details }) {
  return (
    <div style={{
      padding: 'var(--space-4)',
      background: 'var(--bg-elevated)',
      borderRadius: 'var(--radius-md)',
      borderLeft: `3px solid ${color}`,
    }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 'var(--space-2)', marginBottom: 'var(--space-2)' }}>
        <span>{icon}</span>
        <strong style={{ fontSize: '0.875rem', color: 'var(--text-primary)' }}>{name}</strong>
      </div>
      <ul style={{ listStyle: 'none', display: 'flex', flexDirection: 'column', gap: 4 }}>
        {details.map(d => (
          <li key={d} style={{ fontSize: '0.78rem', color: 'var(--text-secondary)', display: 'flex', gap: 6 }}>
            <span style={{ color }}>›</span>
            {d}
          </li>
        ))}
      </ul>
    </div>
  );
}
