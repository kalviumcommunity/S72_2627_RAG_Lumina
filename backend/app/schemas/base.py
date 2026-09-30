"""Shared base for API schemas.

Response fields with defaults (e.g. `citations: list = []`) are always present in responses, so
the serialization JSON schema marks them required — the generated TypeScript types are then exact
(no needless `?`). Request validation is unaffected: defaults stay optional on input.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class APIModel(BaseModel):
    model_config = ConfigDict(json_schema_serialization_defaults_required=True)
