#!/usr/bin/env python3
"""JSON Schemas for the two Layer4 v2 LLM calls (vLLM guided_json)."""

from __future__ import annotations

from typing import Any

from common_v2 import (
    CITATION_FUNCTIONS,
    PAPER_TYPES,
    RELATION_TYPES,
    RESOURCE_KINDS,
    WRAPPING_DIFFICULTIES,
    ACCESS_TYPES,
    AVAILABILITY_STATUSES,
)


def _str() -> dict[str, Any]:
    return {"type": "string"}


def _str_list() -> dict[str, Any]:
    return {"type": "array", "items": {"type": "string"}}


def _text_items() -> dict[str, Any]:
    return {
        "type": "array",
        "items": {
            "type": "object",
            "properties": {"text": _str()},
            "required": ["text"],
            "additionalProperties": False,
        },
    }


def _enum(values: set[str], *, allow_empty: bool = False) -> dict[str, Any]:
    ordered = sorted(values)
    if allow_empty and "" not in ordered:
        ordered = [""] + ordered
    return {"type": "string", "enum": ordered}


EVIDENCE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "section": _str(),
        "quote": _str(),
        "citation_context_ids": _str_list(),
    },
    "required": ["section", "quote"],
    "additionalProperties": False,
}


SEMANTIC_CANDIDATES_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "paper_record": {
            "type": "object",
            "properties": {
                "intent": {
                    "type": "object",
                    "properties": {
                        "paper_type": _enum(PAPER_TYPES),
                        "research_problem": _str(),
                        "target_domain": _str_list(),
                    },
                    "required": ["paper_type", "research_problem", "target_domain"],
                    "additionalProperties": False,
                },
                "contributions": _text_items(),
                "claims": {**_text_items(), "maxItems": 2},
                "experiments": _text_items(),
                "limitations": _text_items(),
                "future_work": _text_items(),
                "citation_functions": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "context_id": _str(),
                            "citation_function": _enum(CITATION_FUNCTIONS, allow_empty=True),
                        },
                        "required": ["context_id", "citation_function"],
                        "additionalProperties": False,
                    },
                },
            },
            "required": [
                "intent",
                "contributions",
                "claims",
                "experiments",
                "limitations",
                "future_work",
                "citation_functions",
            ],
            "additionalProperties": False,
        },
        "resource_candidates": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "kind": _enum(RESOURCE_KINDS),
                    "name": _str(),
                    "aliases": _str_list(),
                    "description": _str(),
                    "relation_type": _enum(RELATION_TYPES),
                    "evidence": EVIDENCE_SCHEMA,
                    "url": _str(),
                    "search_hints": _str_list(),
                    "confidence": {"type": "string", "enum": ["high", "medium", "low"]},
                },
                "required": [
                    "kind",
                    "name",
                    "description",
                    "relation_type",
                    "evidence",
                    "url",
                    "search_hints",
                    "confidence",
                ],
                "additionalProperties": False,
            },
        },
        "warnings": _str_list(),
    },
    "required": ["paper_record", "resource_candidates", "warnings"],
    "additionalProperties": False,
}


JUDGED_RESOURCES_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "resources": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "kind": _enum(RESOURCE_KINDS),
                    "name": _str(),
                    "aliases": _str_list(),
                    "description": _str(),
                    "relation_type": _enum(RELATION_TYPES),
                    "evidence_section": _str(),
                    "evidence_quote": _str(),
                    "citation_context_ids": _str_list(),
                    "url": _str(),
                    "access_type": _enum(ACCESS_TYPES),
                    "license": _str(),
                    "availability_status": _enum(AVAILABILITY_STATUSES),
                    "availability_notes": _str(),
                    "agent_callable": {
                        "type": "object",
                        "properties": {
                            "can_wrap": {"type": "boolean"},
                            "estimated_wrapping_difficulty": _enum(WRAPPING_DIFFICULTIES),
                            "notes": _str(),
                        },
                        "required": ["can_wrap", "estimated_wrapping_difficulty", "notes"],
                        "additionalProperties": False,
                    },
                    "confidence": {"type": "string", "enum": ["high", "medium", "low"]},
                },
                "required": [
                    "kind",
                    "name",
                    "description",
                    "relation_type",
                    "evidence_section",
                    "evidence_quote",
                    "url",
                    "access_type",
                    "license",
                    "availability_status",
                    "availability_notes",
                    "agent_callable",
                    "confidence",
                ],
                "additionalProperties": False,
            },
        },
        "warnings": _str_list(),
    },
    "required": ["resources", "warnings"],
    "additionalProperties": False,
}
