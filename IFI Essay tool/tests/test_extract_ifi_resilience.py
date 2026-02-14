import sys
import types

from pipeline import extract_ifi


class _RaisingCompletions:
    @staticmethod
    def create(*args, **kwargs):
        raise RuntimeError("Connection error")


class _RaisingClient:
    def __init__(self, *args, **kwargs):
        self.chat = types.SimpleNamespace(completions=_RaisingCompletions())


def test_llm_failure_disables_retries_and_falls_back(monkeypatch, caplog):
    extract_ifi._reset_llm_runtime_state_for_tests()

    fake_openai = types.SimpleNamespace(OpenAI=_RaisingClient)
    monkeypatch.setitem(sys.modules, "openai", fake_openai)
    monkeypatch.setenv("OPENAI_API_KEY", "fake-key")
    monkeypatch.delenv("GROQ_API_KEY", raising=False)

    with caplog.at_level("WARNING"):
        first = extract_ifi.extract_ifi_submission("School: Lincoln\nGrade: 8")
        second = extract_ifi.extract_ifi_submission("School: Lincoln\nGrade: 8")
        third = extract_ifi.extract_ifi_submission("School: Lincoln\nGrade: 8")

    assert first["extraction_method"] == "fallback"
    assert second["extraction_method"] == "fallback"
    assert third["extraction_method"] == "fallback"

    first_notes = " ".join(first.get("notes", []))
    second_notes = " ".join(second.get("notes", []))
    assert "Fallback reason: llm_error:" in first_notes
    assert "Fallback reason: llm_runtime_disabled:" in second_notes

    warning_messages = [r.message for r in caplog.records if r.levelname == "WARNING"]
    assert any("IFI LLM extraction failed, switching to fallback mode" in m for m in warning_messages)
    assert any("IFI LLM extraction disabled for this process" in m for m in warning_messages)
    # Third call should not emit additional disabled warning spam
    assert sum(1 for m in warning_messages if "disabled for this process" in m) == 1


def test_no_key_warning_emitted_once(monkeypatch, caplog):
    extract_ifi._reset_llm_runtime_state_for_tests()
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("GROQ_API_KEY", raising=False)

    with caplog.at_level("WARNING"):
        extract_ifi.extract_ifi_submission("short")
        extract_ifi.extract_ifi_submission("short")

    warning_messages = [r.message for r in caplog.records if r.levelname == "WARNING"]
    assert sum(1 for m in warning_messages if "No LLM API keys set" in m) == 1
