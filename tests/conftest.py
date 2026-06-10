"""Shared pytest configuration."""

from pathlib import Path

import pytest


def pytest_configure(config: pytest.Config) -> None:
    config.option.basetemp = str(Path(config.rootpath) / ".pytest-tmp")
