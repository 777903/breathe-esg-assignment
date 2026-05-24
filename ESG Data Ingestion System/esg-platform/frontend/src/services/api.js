/**
 * api.js — Central API service layer
 *
 * All backend communication goes through this file.
 * Components never call fetch() directly.
 *
 * Pattern: each function returns a Promise that resolves to data
 * or throws an Error with a human-readable message.
 */

const BASE_URL = '/api';

/**
 * Generic request helper with consistent error handling.
 */
async function request(path, options = {}) {
  const url = `${BASE_URL}${path}`;
  const response = await fetch(url, {
    headers: {
      'Accept': 'application/json',
      ...options.headers,
    },
    ...options,
  });

  if (!response.ok) {
    let message = `HTTP ${response.status}: ${response.statusText}`;
    try {
      const errorBody = await response.json();
      message = errorBody.error || errorBody.detail || JSON.stringify(errorBody);
    } catch (_) {
      // JSON parse failed — use status text
    }
    throw new Error(message);
  }

  // Handle 204 No Content
  if (response.status === 204) return null;
  return response.json();
}

// ---------------------------------------------------------------------------
// Data Sources
// ---------------------------------------------------------------------------

/**
 * Fetch available data sources for the upload form dropdown.
 * @returns {Promise<DataSource[]>}
 */
export async function fetchDataSources() {
  return request('/datasources/');
}

// ---------------------------------------------------------------------------
// Upload
// ---------------------------------------------------------------------------

/**
 * Upload a CSV file for ingestion.
 * @param {File}   file          - The CSV file object
 * @param {string} dataSourceId  - UUID of the target DataSource
 * @returns {Promise<IngestionSummary>}
 */
export async function uploadFile(file, dataSourceId) {
  const formData = new FormData();
  formData.append('file', file);
  formData.append('data_source_id', dataSourceId);

  return request('/upload/', {
    method: 'POST',
    body: formData,
    // Do NOT set Content-Type — browser sets multipart boundary automatically
  });
}

// ---------------------------------------------------------------------------
// Records
// ---------------------------------------------------------------------------

/**
 * List emission records with optional filters and pagination.
 * @param {object} params - { source, status, scope, page, page_size }
 * @returns {Promise<PaginatedRecords>}
 */
export async function fetchRecords(params = {}) {
  const qs = new URLSearchParams();
  if (params.source)    qs.set('source', params.source);
  if (params.status)    qs.set('status', params.status);
  if (params.scope)     qs.set('scope', params.scope);
  if (params.page)      qs.set('page', params.page);
  if (params.page_size) qs.set('page_size', params.page_size);

  const query = qs.toString() ? `?${qs.toString()}` : '';
  return request(`/records/${query}`);
}

/**
 * Fetch records with status 'error' or 'suspicious' (issues list).
 * @returns {Promise<IssuesResponse>}
 */
export async function fetchIssues() {
  return request('/records/issues/');
}

/**
 * Fetch full detail of a single record including validation errors.
 * @param {string} recordId - UUID
 * @returns {Promise<EmissionRecordDetail>}
 */
export async function fetchRecord(recordId) {
  return request(`/records/${recordId}/`);
}

/**
 * Approve a record (transitions status to 'approved').
 * @param {string} recordId - UUID
 * @returns {Promise<EmissionRecordDetail>}
 */
export async function approveRecord(recordId) {
  return request(`/records/${recordId}/approve/`, { method: 'POST' });
}

// ---------------------------------------------------------------------------
// Dashboard
// ---------------------------------------------------------------------------

/**
 * Fetch dashboard aggregate statistics.
 * @returns {Promise<DashboardData>}
 */
export async function fetchDashboard() {
  return request('/dashboard/');
}

// ---------------------------------------------------------------------------
// Audit
// ---------------------------------------------------------------------------

/**
 * Fetch the audit trail for a specific record.
 * @param {string} recordId - UUID
 * @returns {Promise<AuditResponse>}
 */
export async function fetchAuditLog(recordId) {
  return request(`/audit/${recordId}/`);
}

// ---------------------------------------------------------------------------
// Development helper
// ---------------------------------------------------------------------------

/**
 * POST /api/seed/ — creates demo org + data sources.
 * Only used during development setup.
 */
export async function seedDemoData() {
  return request('/seed/', { method: 'POST' });
}
