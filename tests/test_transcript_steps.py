from app.services.steps import from_transcript


def test_steps_fallback_preserves_order_and_source_text(app):
    with app.app_context():
        result = from_transcript("Boil water. Add the grains.\nServe warm.")

    assert result == {
        "steps": ["Boil water.", "Add the grains.", "Serve warm."],
        "mode": "heuristic",
    }
