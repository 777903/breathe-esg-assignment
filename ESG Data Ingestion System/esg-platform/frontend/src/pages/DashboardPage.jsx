/**
 * DashboardPage — analyst review dashboard.
 *
 * Shows:
 *   - Summary stat cards (total records, CO2e, status breakdown)
 *   - Scope CO2e breakdown
 *   - Full records table with filters and approve actions
 */

import React, { useState, useEffect } from 'react';
import { fetchDashboard } from '../services/api';
import { useRecords } from '../hooks/useRecords';
import DataTable from '../components/DataTable';
import Filters from '../components/Filters';
import StatusBadge from '../components/StatusBadge';

function StatCard({ label, value, sub, accentColor, icon }) {
  return (
    <div className="stat-card fade-in-up" style={{ '--accent-color': accentColor }}>
      <div className="stat-label">{label}</div>
      <div className="stat-value">{value}</div>
      {sub && <div className="stat-sub">{sub}</div>}
    </div>
  );
}

function ScopeBar({ scope1, scope2, scope3 }) {
  const total = (scope1 || 0) + (scope2 || 0) + (scope3 || 0);
  if (total === 0) return null;

  const pct = (v) => ((v || 0) / total * 100).toFixed(1);
  const fmt = (v) => v >= 1000 ? `${(v / 1000).toFixed(1)} tCO₂e` : `${Math.round(v)} kgCO₂e`;

  return (
    <div className="card mb-6">
      <div className="card-header">
        <h3 className="card-title">CO₂e by GHG Scope</h3>
        <span style={{ fontSize: '0.8rem', color: 'var(--text-muted)' }}>
          Total: {fmt(total)}
        </span>
      </div>
      <div style={{ display: 'flex', gap: 4, marginBottom: 'var(--space-4)', height: 12, borderRadius: 6, overflow: 'hidden' }}>
        {scope1 > 0 && <div style={{ flex: scope1, background: 'var(--scope1)', transition: 'flex 0.5s ease' }} title={`Scope 1: ${pct(scope1)}%`} />}
        {scope2 > 0 && <div style={{ flex: scope2, background: 'var(--scope2)', transition: 'flex 0.5s ease' }} title={`Scope 2: ${pct(scope2)}%`} />}
        {scope3 > 0 && <div style={{ flex: scope3, background: 'var(--scope3)', transition: 'flex 0.5s ease' }} title={`Scope 3: ${pct(scope3)}%`} />}
      </div>
      <div style={{ display: 'flex', gap: 'var(--space-6)' }}>
        {[
          { key: 'scope1', label: 'Scope 1 Direct', value: scope1, color: 'var(--scope1)' },
          { key: 'scope2', label: 'Scope 2 Electricity', value: scope2, color: 'var(--scope2)' },
          { key: 'scope3', label: 'Scope 3 Indirect', value: scope3, color: 'var(--scope3)' },
        ].map(s => (
          <div key={s.key}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 2 }}>
              <div style={{ width: 10, height: 10, borderRadius: 2, background: s.color }} />
              <span style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>{s.label}</span>
            </div>
            <div style={{ fontSize: '0.9rem', fontWeight: 600, color: 'var(--text-primary)' }}>
              {fmt(s.value || 0)}
            </div>
            <div style={{ fontSize: '0.72rem', color: 'var(--text-muted)' }}>{pct(s.value)}%</div>
          </div>
        ))}
      </div>
    </div>
  );
}

export default function DashboardPage() {
  const [dashData, setDashData] = useState(null);
  const [dashLoading, setDashLoading] = useState(true);

  const {
    records, loading, error, filters, updateFilters,
    page, setPage, totalCount, totalPages, approve, reload,
  } = useRecords({ source: '', status: '', scope: '' });

  useEffect(() => {
    loadDashboard();
  }, []);

  // Reload dashboard stats when records change (e.g. after approval)
  useEffect(() => {
    if (!loading) loadDashboard();
  }, [loading]);

  async function loadDashboard() {
    setDashLoading(true);
    try {
      const data = await fetchDashboard();
      setDashData(data);
    } catch (_) {
      // Dashboard stats are informational — don't block the table
    } finally {
      setDashLoading(false);
    }
  }

  async function handleApprove(recordId) {
    await approve(recordId);
    // Refresh dashboard stats
    loadDashboard();
  }

  const statusCounts = dashData?.status_counts || {};
  const scopeCo2e = dashData?.scope_co2e || {};

  return (
    <div className="fade-in">
      {/* Page header */}
      <div className="section-header mb-6">
        <div className="section-title">
          <span className="section-icon">📊</span>
          <div>
            <h1>Review Dashboard</h1>
            <p style={{ marginTop: 4 }}>
              Analyst review queue for normalized emission records
            </p>
          </div>
        </div>
        <button
          id="btn-refresh-dashboard"
          className="btn btn-ghost"
          onClick={() => { reload(); loadDashboard(); }}
        >
          ↻ Refresh
        </button>
      </div>

      {/* Stat cards */}
      <div className="stat-grid">
        <StatCard
          label="Total Records"
          value={(dashData?.total_records || 0).toLocaleString()}
          sub="across all sources"
          accentColor="var(--accent-blue)"
        />
        <StatCard
          label="Total CO₂e"
          value={
            dashData?.total_co2e_kg >= 1000
              ? `${(dashData.total_co2e_kg / 1000).toFixed(1)}t`
              : `${Math.round(dashData?.total_co2e_kg || 0)} kg`
          }
          sub="CO₂ equivalent"
          accentColor="var(--accent-teal)"
        />
        <StatCard
          label="Valid"
          value={(statusCounts.valid || 0).toLocaleString()}
          sub="ready to approve"
          accentColor="var(--status-valid)"
        />
        <StatCard
          label="Errors"
          value={(statusCounts.error || 0).toLocaleString()}
          sub="need resolution"
          accentColor="var(--status-error)"
        />
        <StatCard
          label="Suspicious"
          value={(statusCounts.suspicious || 0).toLocaleString()}
          sub="need analyst review"
          accentColor="var(--status-suspicious)"
        />
        <StatCard
          label="Approved"
          value={(statusCounts.approved || 0).toLocaleString()}
          sub="confirmed records"
          accentColor="var(--status-approved)"
        />
      </div>

      {/* Scope CO2e breakdown */}
      <ScopeBar
        scope1={scopeCo2e.scope1}
        scope2={scopeCo2e.scope2}
        scope3={scopeCo2e.scope3}
      />

      {/* Records table */}
      <div className="card">
        <div className="card-header">
          <h3 className="card-title">Emission Records</h3>
          {error && <span style={{ color: 'var(--status-error)', fontSize: '0.8rem' }}>Error: {error}</span>}
        </div>

        <Filters
          filters={filters}
          onFilterChange={updateFilters}
          totalCount={totalCount}
        />

        <DataTable
          records={records}
          loading={loading}
          onApprove={handleApprove}
          page={page}
          totalPages={totalPages}
          totalCount={totalCount}
          onPageChange={setPage}
        />
      </div>
    </div>
  );
}
