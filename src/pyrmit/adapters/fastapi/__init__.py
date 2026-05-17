"""FastAPI adapter: ``require_policy`` dependency factory."""

from __future__ import annotations

from pyrmit.adapters.fastapi.dependency import HttpDenial, require_policy
from pyrmit.core.errors import ConfigurationError

__all__ = ["ConfigurationError", "HttpDenial", "require_policy"]
