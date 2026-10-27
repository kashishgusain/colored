import json

import pytest

from app.services import summarization
from app.services.errors import ServiceError


def test_analyze_returns_grounded_suggestions_from_allowed_categories(app, monkeypatch):
    response = {
        "summary": "Families sow seven grains before the monsoon.",
        "tags": ["harela", "monsoon tradition"],
        "suggested_category_slug": "traditions",
        "metadata": {"festivals": ["Harela"], "places": ["Kumaon"]},
    }
    monkeypatch.setattr(summarization.llm, "llm_configured", lambda: True)
    monkeypatch.setattr(summarization.llm, "chat", lambda *args, **kwargs: json.dumps(response))

    result = summarization.analyze(
        "Families sow seven grains in a basket before the monsoon and later place the green shoots at home.",
        "Harela", "Folk Stories", "kumaoni", [("traditions", "Festivals & Traditions")],
    )

    assert result["summary"] == response["summary"]
    assert result["tags"] == response["tags"]
    assert result["suggested_category"] == {"slug": "traditions", "name": "Festivals & Traditions"}
    assert result["metadata"]["festivals"] == ["Harela"]


def test_analyze_discards_category_outside_active_choices(app, monkeypatch):
    response = {"summary": "A supported summary.", "tags": [], "suggested_category_slug": "medicine"}
    monkeypatch.setattr(summarization.llm, "llm_configured", lambda: True)
    monkeypatch.setattr(summarization.llm, "chat", lambda *args, **kwargs: json.dumps(response))

    result = summarization.analyze("A sufficiently long source description about a local practice.",
                                   "A practice", "Traditions", "hindi", [("traditions", "Traditions")])

    assert result["suggested_category"] is None


def test_analyze_rejects_insufficient_source_without_calling_provider(monkeypatch):
    monkeypatch.setattr(summarization.llm, "chat", lambda *args, **kwargs: pytest.fail("provider should not run"))

    with pytest.raises(ServiceError) as exc:
        summarization.analyze("Too short", "Title", "Category", "hindi")

    assert exc.value.code == "INSUFFICIENT_SOURCE"