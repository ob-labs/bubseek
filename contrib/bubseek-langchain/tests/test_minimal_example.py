from __future__ import annotations

import importlib.util

import pytest

pytestmark = pytest.mark.skipif(
    importlib.util.find_spec("langchain_core") is None,
    reason="langchain_core is not installed in the root test environment",
)


def test_minimal_runnable_factory_is_importable() -> None:
    from bubseek_langchain.examples.minimal_runnable import minimal_lc_agent

    assert callable(minimal_lc_agent)
