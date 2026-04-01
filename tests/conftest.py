import os
import pytest


@pytest.fixture(autouse=True)
def enable_mainnet_for_tests():
    """Globally enable Binance Mainnet profile for the test suite."""
    os.environ["BINANCE_FUTURES_ENABLE_MAINNET"] = "true"
    yield
    # We could delete it, but better stay enabled during test session
