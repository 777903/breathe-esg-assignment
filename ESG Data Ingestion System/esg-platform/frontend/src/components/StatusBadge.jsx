/**
 * StatusBadge — displays a colored pill badge for record status or GHG scope.
 *
 * Props:
 *   type:  'status' | 'scope' | 'severity'
 *   value: 'valid' | 'error' | 'suspicious' | 'approved' | 'pending'
 *          'scope1' | 'scope2' | 'scope3'
 *          'error' | 'warning'
 */

import React from 'react';

const STATUS_CONFIG = {
  valid:      { label: 'Valid',       icon: '✓', className: 'badge-valid' },
  error:      { label: 'Error',       icon: '✕', className: 'badge-error' },
  suspicious: { label: 'Suspicious',  icon: '⚠', className: 'badge-suspicious' },
  approved:   { label: 'Approved',    icon: '✓', className: 'badge-approved' },
  pending:    { label: 'Pending',     icon: '·', className: 'badge-pending' },
};

const SCOPE_CONFIG = {
  scope1: { label: 'Scope 1', className: 'badge-scope1' },
  scope2: { label: 'Scope 2', className: 'badge-scope2' },
  scope3: { label: 'Scope 3', className: 'badge-scope3' },
};

const SEVERITY_CONFIG = {
  error:   { label: 'Error',   className: 'badge-error' },
  warning: { label: 'Warning', className: 'badge-suspicious' },
};

export default function StatusBadge({ type = 'status', value }) {
  let config;

  if (type === 'scope') {
    config = SCOPE_CONFIG[value] || { label: value, className: 'badge-pending' };
  } else if (type === 'severity') {
    config = SEVERITY_CONFIG[value] || { label: value, className: 'badge-pending' };
  } else {
    config = STATUS_CONFIG[value] || { label: value, icon: '?', className: 'badge-pending' };
  }

  return (
    <span className={`badge ${config.className}`}>
      <span className="badge-dot" />
      {config.icon && <span style={{ fontSize: '0.7rem' }}>{config.icon}</span>}
      {config.label}
    </span>
  );
}
