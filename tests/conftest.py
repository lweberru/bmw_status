"""Shared test bootstrap for the BMW Status custom component."""

import sys
from pathlib import Path

import pytest


sys.path.insert(0, str(Path(__file__).parents[1]))


@pytest.fixture(autouse=True)
def enable_bmw_status_custom_integration(enable_custom_integrations):
	"""Allow config-flow tests to load the workspace custom integration."""