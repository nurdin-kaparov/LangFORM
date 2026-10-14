"""LangFORM local-first Context Intelligence package."""

from .core import ContextSubagent, LangFORM
from .models import MODEL_CATALOG, ModelManager, ModelError
from .schemas import AssetRecord, ContextFrame, ContextPackage, SourceCoordinates, GridCoordinates, ParagraphCoordinates

__version__ = "0.3.0"

__all__ = [
    "ContextSubagent",
    "LangFORM",
    "AssetRecord",
    "ContextFrame",
    "ContextPackage",
    "SourceCoordinates",
    "GridCoordinates",
    "ParagraphCoordinates",
    "ModelManager",
    "ModelError",
    "MODEL_CATALOG",
]
