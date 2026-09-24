"""Section tree models."""

from __future__ import annotations

from pydantic import BaseModel, Field


class SectionNode(BaseModel):
    """A hierarchical section node."""

    title: str
    level: int = Field(..., ge=1, le=6)
    anchor: str | None = None
    html: str | None = None
    markdown: str | None = None
    children: list["SectionNode"] = Field(default_factory=list)
