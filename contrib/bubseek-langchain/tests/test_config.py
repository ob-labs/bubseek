from __future__ import annotations

import pytest
from bubseek_langchain.config import LangchainPluginSettings, validate_config
from bubseek_langchain.errors import LangchainConfigError


def test_validate_runnable_requires_factory() -> None:
    settings = LangchainPluginSettings(mode="runnable", factory=None)
    with pytest.raises(LangchainConfigError, match="BUB_LANGCHAIN_FACTORY"):
        validate_config(settings)


def test_validate_runnable_ok_with_factory() -> None:
    settings = LangchainPluginSettings(mode="runnable", factory="builtins:str")
    validate_config(settings)
