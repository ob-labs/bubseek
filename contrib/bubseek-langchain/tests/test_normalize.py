from __future__ import annotations

from types import SimpleNamespace

from bubseek_langchain.normalize import normalize_langchain_output


def test_normalize_str() -> None:
    assert normalize_langchain_output("hello") == "hello"


def test_normalize_message_like_object() -> None:
    message = SimpleNamespace(content="hello")
    assert normalize_langchain_output(message) == "hello"


def test_normalize_dict_messages() -> None:
    payload = {
        "messages": [
            {"content": "alpha"},
            {"content": [{"text": "beta"}]},
        ]
    }
    assert normalize_langchain_output(payload) == "alpha\nbeta"
