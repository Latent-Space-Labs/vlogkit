"""Unit tests for the storyboard agents (Director / Editor / Polisher)."""

from __future__ import annotations

import pytest

from vlogkit.storyboard.agents.base import AgentError, parse_json_response


def test_agent_error_records_stage_and_reason():
    err = AgentError(stage="director", reason="missing field")
    assert err.stage == "director"
    assert err.reason == "missing field"
    assert "director" in str(err)
    assert "missing field" in str(err)


def test_parse_json_response_plain_json():
    raw = '{"title": "Test", "sections": []}'
    assert parse_json_response(raw) == {"title": "Test", "sections": []}


def test_parse_json_response_strips_json_fence():
    raw = '```json\n{"title": "Test"}\n```'
    assert parse_json_response(raw) == {"title": "Test"}


def test_parse_json_response_strips_unlabeled_fence():
    raw = '```\n{"title": "Test"}\n```'
    assert parse_json_response(raw) == {"title": "Test"}


def test_parse_json_response_raises_value_error_on_garbage():
    with pytest.raises(ValueError):
        parse_json_response("this is not json")
