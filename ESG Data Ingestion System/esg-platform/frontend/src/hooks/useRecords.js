/**
 * useRecords — custom hook for fetching and managing emission records.
 *
 * Encapsulates:
 * - Data fetching with filters
 * - Pagination state
 * - Loading / error states
 * - Approve action
 *
 * Components using this hook don't need to know about the API layer.
 */

import { useState, useEffect, useCallback } from 'react';
import { fetchRecords, approveRecord as apiApprove } from '../services/api';

/**
 * @param {object} initialFilters - { source, status, scope }
 */
export function useRecords(initialFilters = {}) {
  const [records, setRecords] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [filters, setFilters] = useState(initialFilters);
  const [page, setPage] = useState(1);
  const [totalCount, setTotalCount] = useState(0);
  const PAGE_SIZE = 50;

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await fetchRecords({ ...filters, page, page_size: PAGE_SIZE });
      setRecords(data.results);
      setTotalCount(data.count);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }, [filters, page]);

  useEffect(() => {
    load();
  }, [load]);

  const updateFilters = useCallback((newFilters) => {
    setFilters(newFilters);
    setPage(1); // Reset to page 1 on filter change
  }, []);

  const approve = useCallback(async (recordId) => {
    try {
      const updated = await apiApprove(recordId);
      // Optimistically update the record in the local list
      setRecords(prev =>
        prev.map(r => r.id === recordId ? { ...r, status: 'approved', status_display: 'Approved' } : r)
      );
      return updated;
    } catch (err) {
      throw err; // Let calling component handle the error display
    }
  }, []);

  const totalPages = Math.ceil(totalCount / PAGE_SIZE);

  return {
    records,
    loading,
    error,
    filters,
    updateFilters,
    page,
    setPage,
    totalCount,
    totalPages,
    approve,
    reload: load,
  };
}
