from abc import ABC, abstractmethod
from typing import Any


class BaseTranslator(ABC):
    """Contract for RAFAM -> Paxapos payload translators."""

    @property
    @abstractmethod
    def endpoint_path(self) -> str:
        """Relative endpoint path after tenant base URL."""

    @abstractmethod
    def translate(self, columns: list[str], row: tuple[Any, ...]) -> dict[str, Any]:
        """Translate one Oracle row into Paxapos JSON payload."""

    def _row_to_raw(self, columns: list[str], row: tuple[Any, ...]) -> dict[str, Any]:
        """Build a dictionary from cursor columns and row values."""
        return dict(zip(columns, row))
