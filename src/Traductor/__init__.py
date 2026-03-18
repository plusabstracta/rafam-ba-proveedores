from .base import BaseTranslator
from .proveedores import ProveedoresTranslator

TRANSLATOR_REGISTRY: dict[str, BaseTranslator] = {
    "proveedores": ProveedoresTranslator(),
}

__all__ = ["BaseTranslator", "ProveedoresTranslator", "TRANSLATOR_REGISTRY"]
