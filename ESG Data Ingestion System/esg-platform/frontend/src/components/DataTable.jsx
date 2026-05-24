/**
 * DataTable — displays emission records in a sortable, filterable table.
 *
 * Props:
 *   records:   EmissionRecord[]
 *   loading:   boolean
 *   onApprove: function(recordId) => Promise
 *   page:      current page number
 *   totalPages: total page count
 *   totalCount: total matching records
 *   onPageChange: function(page)
 */

import React, { useState } from 'react';
import StatusBadge from './StatusBadge';

function formatNumber(value, decimals = 2) {
  if (value === null || value === undefined) return '—';
  return Number(value).toLocaleString(undefined, {
    minimumFractionDigits: 0,
    maximumFractionDigits: decimals,
  });
}

function formatDate(dateStr) {
  if (!dateStr) return '—';
  return new Date(dateStr).toLocaleDateString('en-GB', {
    day: '2-digit', month: 'short', year: 'numeric',
  });
}

function RowErrors({ errors }) {
  if (!errors || errors.length === 0) return null;
  return (
    <ul className="error-list">
      {errors.map(err => (
        <li key={err.id} className={`error-item severity-${err.severity}`}>
          <span style={{ fontWeight: 700 }}>{err.rule_code}</span>
          <span>{err.message}</span>
        </li>
      ))}
    </ul>
  );
}

function TableRow({ record, onApprove }) {
  const [expanded, setExpanded] = useState(false);
  const [approving, setApproving] = useState(false);

  const rowClass = [
    record.status === 'error' ? 'row-error' : '',
    record.status === 'suspicious' ? 'row-suspicious' : '',
    record.status === 'approved' ? 'row-approved' : '',
  ].filter(Boolean).join(' ');

  async function handleApprove(e) {
    e.stopPropagation();
    setApproving(true);
    try {
      await onApprove(record.id);
    } catch (err) {
      alert(`Approval failed: ${err.message}`);
    } finally {
      setApproving(false);
    }
  }

  const canApprove = ['valid', 'suspicious'].includes(record.status);
  const hasErrors = record.error_count > 0 || record.warning_count > 0;

  return (
    <>
      <tr
        className={rowClass}
        onClick={() => hasErrors && setExpanded(e => !e)}
        style={{ cursor: hasErrors ? 'pointer' : 'default' }}
      >
        <td>
          <StatusBadge type="status" value={record.status} />
        </td>
        <td>
          <StatusBadge type="scope" value={record.scope} />
        </td>
        <td>
          <span className="mono" style={{ fontSize: '0.78rem', color: 'var(--text-secondary)' }}>
            {record.source_type}
          </span>
          <br />
          <span style={{ fontSize: '0.82rem' }}>{record.source_name}</span>
        </td>
        <td style={{ color: 'var(--text-secondary)', fontSize: '0.82rem' }}>
          {record.category.replace(/_/g, ' ')}
        </td>
        <td className="mono">
          <span style={{ color: 'var(--text-primary)', fontWeight: 500 }}>
            {formatNumber(record.original_value)}
          </span>
          {' '}
          <span style={{ color: 'var(--text-muted)', fontSize: '0.78rem' }}>
            {record.original_unit}
          </span>
          {record.original_unit !== record.quantity_unit && (
            <span style={{ color: 'var(--text-muted)', fontSize: '0.75rem', display: 'block' }}>
              → {formatNumber(record.quantity_value)} {record.quantity_unit}
            </span>
          )}
        </td>
        <td className="mono">
          {record.co2e_kg !== null ? (
            <span style={{ color: 'var(--accent-teal)', fontWeight: 600 }}>
              {formatNumber(record.co2e_kg)} kg
            </span>
          ) : (
            <span style={{ color: 'var(--text-muted)' }}>N/A</span>
          )}
        </td>
        <td style={{ color: 'var(--text-secondary)', fontSize: '0.82rem' }}>
          {formatDate(record.activity_date)}
        </td>
        <td>
          {record.error_count > 0 && (
            <span className="badge badge-error" style={{ marginRight: 4 }}>
              {record.error_count} err
            </span>
          )}
          {record.warning_count > 0 && (
            <span className="badge badge-suspicious">
              {record.warning_count} warn
            </span>
          )}
        </td>
        <td onClick={e => e.stopPropagation()}>
          {canApprove && (
            <button
              id={`btn-approve-${record.id}`}
              className="btn btn-success btn-sm"
              onClick={handleApprove}
              disabled={approving}
            >
              {approving ? '...' : '✓ Approve'}
            </button>
          )}
          {record.status === 'approved' && (
            <span style={{ color: 'var(--status-approved)', fontSize: '0.8rem' }}>Approved ✓</span>
          )}
        </td>
      </tr>
      {expanded && (
        <tr>
          <td colSpan={9} style={{ padding: '0 16px 16px', background: 'rgba(0,0,0,0.2)' }}>
            <RowErrors errors={[]} />
            <div style={{ fontSize: '0.78rem', color: 'var(--text-muted)', paddingTop: 8 }}>
              Click row to toggle · ID: <span className="mono">{record.id}</span>
            </div>
          </td>
        </tr>
      )}
    </>
  );
}

export default function DataTable({
  records,
  loading,
  onApprove,
  page,
  totalPages,
  totalCount,
  onPageChange,
}) {
  if (loading) {
    return (
      <div className="loading-center">
        <div className="spinner" />
        <p>Loading records...</p>
      </div>
    );
  }

  if (!records || records.length === 0) {
    return (
      <div className="loading-center">
        <span style={{ fontSize: '2.5rem' }}>📭</span>
        <p>No records found. Try adjusting filters or upload a file.</p>
      </div>
    );
  }

  return (
    <div>
      <div className="table-container">
        <table className="data-table" aria-label="Emission records table">
          <thead>
            <tr>
              <th>Status</th>
              <th>Scope</th>
              <th>Source</th>
              <th>Category</th>
              <th>Quantity</th>
              <th>CO₂e</th>
              <th>Date</th>
              <th>Issues</th>
              <th>Action</th>
            </tr>
          </thead>
          <tbody>
            {records.map(record => (
              <TableRow
                key={record.id}
                record={record}
                onApprove={onApprove}
              />
            ))}
          </tbody>
        </table>
      </div>

      {totalPages > 1 && (
        <div className="pagination">
          <span className="pagination-info">
            Page {page} of {totalPages} · {totalCount.toLocaleString()} total records
          </span>
          <div className="pagination-controls">
            <button
              id="btn-prev-page"
              className="btn btn-ghost btn-sm"
              onClick={() => onPageChange(page - 1)}
              disabled={page <= 1}
            >
              ← Prev
            </button>
            <button
              id="btn-next-page"
              className="btn btn-ghost btn-sm"
              onClick={() => onPageChange(page + 1)}
              disabled={page >= totalPages}
            >
              Next →
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
