/**
 * UploadForm — handles file selection and upload to the backend.
 *
 * Props:
 *   dataSources:  DataSource[] — list for the dropdown
 *   onUploadSuccess: function(summary) — called after successful upload
 */

import React, { useState, useRef } from 'react';
import { uploadFile } from '../services/api';

export default function UploadForm({ dataSources = [], onUploadSuccess }) {
  const [selectedFile, setSelectedFile] = useState(null);
  const [dataSourceId, setDataSourceId] = useState('');
  const [dragging, setDragging] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [result, setResult] = useState(null);
  const [error, setError] = useState(null);
  const fileInputRef = useRef(null);

  function handleFileChange(e) {
    const file = e.target.files[0];
    if (file) {
      setSelectedFile(file);
      setResult(null);
      setError(null);
    }
  }

  function handleDrop(e) {
    e.preventDefault();
    setDragging(false);
    const file = e.dataTransfer.files[0];
    if (file) {
      setSelectedFile(file);
      setResult(null);
      setError(null);
    }
  }

  async function handleSubmit(e) {
    e.preventDefault();

    if (!selectedFile) {
      setError('Please select a CSV file to upload.');
      return;
    }
    if (!dataSourceId) {
      setError('Please select a data source.');
      return;
    }

    setUploading(true);
    setError(null);
    setResult(null);

    try {
      const summary = await uploadFile(selectedFile, dataSourceId);
      setResult(summary);
      setSelectedFile(null);
      if (fileInputRef.current) fileInputRef.current.value = '';
      onUploadSuccess?.(summary);
    } catch (err) {
      setError(err.message);
    } finally {
      setUploading(false);
    }
  }

  return (
    <form id="upload-form" onSubmit={handleSubmit}>
      {/* Data source selector */}
      <div className="form-group mb-4">
        <label className="form-label" htmlFor="data-source-select">
          Data Source
        </label>
        <select
          id="data-source-select"
          className="form-select"
          value={dataSourceId}
          onChange={e => setDataSourceId(e.target.value)}
          disabled={uploading}
        >
          <option value="">Select a data source...</option>
          {dataSources.map(ds => (
            <option key={ds.id} value={ds.id}>
              {ds.name} ({ds.source_type})
            </option>
          ))}
        </select>
      </div>

      {/* Drop zone */}
      <div
        className={`drop-zone ${dragging ? 'dragging' : ''}`}
        onDragOver={e => { e.preventDefault(); setDragging(true); }}
        onDragLeave={() => setDragging(false)}
        onDrop={handleDrop}
        onClick={() => fileInputRef.current?.click()}
        style={{ marginBottom: 'var(--space-5)' }}
      >
        <input
          ref={fileInputRef}
          type="file"
          accept=".csv"
          onChange={handleFileChange}
          disabled={uploading}
          aria-label="Upload CSV file"
          style={{ display: 'none' }}
        />

        {selectedFile ? (
          <>
            <span className="drop-zone-icon">📄</span>
            <h3>{selectedFile.name}</h3>
            <p>{(selectedFile.size / 1024).toFixed(1)} KB · Click to change</p>
          </>
        ) : (
          <>
            <span className="drop-zone-icon">⬆️</span>
            <h3>Drop CSV here or click to browse</h3>
            <p>Supports SAP exports, utility bills, and travel booking data</p>
            <span className="badge badge-pending">CSV files only</span>
          </>
        )}
      </div>

      {/* Alerts */}
      {error && (
        <div className="alert alert-error mb-4" role="alert">
          <span>⚠</span>
          <span>{error}</span>
        </div>
      )}

      {result && (
        <div className="alert alert-success mb-4" role="status">
          <span>✓</span>
          <div>
            <strong>Upload complete!</strong>
            <div style={{ marginTop: 4, fontSize: '0.85rem' }}>
              {result.created} records ingested &nbsp;·&nbsp;
              <span style={{ color: 'var(--status-valid)' }}>{result.valid || 0} valid</span> &nbsp;·&nbsp;
              <span style={{ color: 'var(--status-suspicious)' }}>{result.suspicious || 0} suspicious</span> &nbsp;·&nbsp;
              <span style={{ color: 'var(--status-error)' }}>{result.error || 0} errors</span>
            </div>
          </div>
        </div>
      )}

      {/* Submit */}
      <button
        id="btn-upload-submit"
        type="submit"
        className="btn btn-primary w-full"
        disabled={uploading || !selectedFile || !dataSourceId}
        style={{ justifyContent: 'center' }}
      >
        {uploading ? (
          <>
            <span className="spinner" style={{ width: 16, height: 16, borderWidth: 2 }} />
            Ingesting...
          </>
        ) : (
          <>⬆ Ingest Data</>
        )}
      </button>
    </form>
  );
}
