"""Shared pytest configuration."""

from pathlib import Path

import pytest


def pytest_addoption(parser):
    parser.addoption(
        "--run-editor-browser",
        action="store_true",
        default=False,
        help="Run editor browser tests (requires Playwright Chromium).",
    )


def pytest_configure(config: pytest.Config) -> None:
    if config.option.basetemp is None:
        config.option.basetemp = str(Path(config.rootpath) / ".pytest-tmp")
