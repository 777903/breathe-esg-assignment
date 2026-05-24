/**
 * Filters component — filter bar for the records table.
 *
 * Props:
 *   filters:       current filter state { source, status, scope }
 *   onFilterChange: function(newFilters)
 *   totalCount:    total number of matching records
 */

import React from 'react';

const SOURCE_OPTIONS = [
  { value: '', label: 'All Sources' },
  { value: 'sap', label: 'SAP (Fuel & Procurement)' },
  { value: 'utility', label: 'Utility (Electricity)' },
  { value: 'travel', label: 'Corporate Travel' },
];

const STATUS_OPTIONS = [
  { value: '', label: 'All Statuses' },
  { value: 'valid', label: '✓ Valid' },
  { value: 'error', label: '✕ Error' },
  { value: 'suspicious', label: '⚠ Suspicious' },
  { value: 'approved', label: '✓ Approved' },
  { value: 'pending', label: '· Pending' },
];

const SCOPE_OPTIONS = [
  { value: '', label: 'All Scopes' },
  { value: 'scope1', label: 'Scope 1 — Direct' },
  { value: 'scope2', label: 'Scope 2 — Electricity' },
  { value: 'scope3', label: 'Scope 3 — Indirect' },
];

export default function Filters({ filters, onFilterChange, totalCount }) {
  function handleChange(field, value) {
    onFilterChange({ ...filters, [field]: value });
  }

  function clearFilters() {
    onFilterChange({ source: '', status: '', scope: '' });
  }

  const hasActiveFilters = filters.source || filters.status || filters.scope;

  return (
    <div className="filter-bar">
      <span className="filter-label">Filter:</span>

      <select
        id="filter-source"
        className="form-select"
        value={filters.source || ''}
        onChange={e => handleChange('source', e.target.value)}
        aria-label="Filter by data source"
      >
        {SOURCE_OPTIONS.map(opt => (
          <option key={opt.value} value={opt.value}>{opt.label}</option>
        ))}
      </select>

      <select
        id="filter-status"
        className="form-select"
        value={filters.status || ''}
        onChange={e => handleChange('status', e.target.value)}
        aria-label="Filter by status"
      >
        {STATUS_OPTIONS.map(opt => (
          <option key={opt.value} value={opt.value}>{opt.label}</option>
        ))}
      </select>

      <select
        id="filter-scope"
        className="form-select"
        value={filters.scope || ''}
        onChange={e => handleChange('scope', e.target.value)}
        aria-label="Filter by GHG scope"
      >
        {SCOPE_OPTIONS.map(opt => (
          <option key={opt.value} value={opt.value}>{opt.label}</option>
        ))}
      </select>

      {hasActiveFilters && (
        <button
          id="btn-clear-filters"
          className="btn btn-ghost btn-sm"
          onClick={clearFilters}
        >
          ✕ Clear
        </button>
      )}

      <span style={{ marginLeft: 'auto', fontSize: '0.8rem', color: 'var(--text-muted)' }}>
        {totalCount.toLocaleString()} record{totalCount !== 1 ? 's' : ''}
      </span>
    </div>
  );
}
