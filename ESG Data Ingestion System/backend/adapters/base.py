"""
Base adapter contract.

Every source adapter must implement `parse(file_obj) -> list[dict]`.

The returned list contains one dict per row.  Each dict must carry at minimum:
  - `_raw`:  the verbatim row dict (for RawData.payload)
  - `_meta`: ingestion-level metadata (row_number, file_name, etc.)

Additional keys are adapter-specific and consumed by NormalizationService.
"""

import io
from abc import ABC, abstractmethod
from typing import IO


class BaseAdapter(ABC):
    """
    Abstract base class for all source adapters.

    Responsibilities:
      1. Accept a file-like object (CSV, JSON, etc.)
      2. Parse it into a list of normalised-ish dicts (still source-schema)
      3. Do NOT apply emission factors or unit conversion — that is NormalizationService's job.
      4. Do surface obviously malformed values as None so ValidationService can flag them.
    """

    source_type: str = NotImplemented  # must be overridden by subclass

    @abstractmethod
    def parse(self, file_obj: IO[bytes], file_name: str = "unknown") -> list[dict]:
        """
        Parse the uploaded file and return a list of row dicts.

        Each dict must contain:
          _raw        dict   verbatim row (stored in RawData.payload)
          _meta       dict   {row_number, file_name}

        Plus source-specific keys used by NormalizationService.

        Args:
            file_obj:  File-like object (binary or text mode)
            file_name: Original filename for audit purposes

        Returns:
            List of row dicts, one per data row.
        """
        ...

    # ------------------------------------------------------------------ #
    # Shared helpers available to all adapters                             #
    # ------------------------------------------------------------------ #

    @staticmethod
    def safe_float(value, default=None) -> float | None:
        """
        Coerce a value to float, stripping common junk characters.

        Handles:
          - Comma-formatted numbers: "1,234.56"
          - Trailing unit labels: "123 kWh", "45.2 L"
          - Whitespace
          - Explicit "N/A", "-", "" → None
        """
        if value is None:
            return default
        s = str(value).strip().replace(',', '').split()[0]  # take first token
        if s.lower() in ('n/a', 'na', '-', '', 'none', 'null', '#n/a'):
            return default
        try:
            return float(s)
        except ValueError:
            return default

    @staticmethod
    def safe_str(value, default='') -> str:
        """Strip and return string, replacing None/NaN with default."""
        if value is None:
            return default
        s = str(value).strip()
        return default if s.lower() in ('nan', 'none', 'null', 'n/a') else s
