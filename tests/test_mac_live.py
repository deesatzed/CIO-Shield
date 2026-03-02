import os

import pytest

from cognitiveio.runtime.mac_bridge import mac_runtime_available


@pytest.mark.live_mac
def test_mac_runtime_live_available():
    if os.getenv("COGNITIVEIO_ENABLE_LIVE_MAC_TESTS", "0") != "1":
        pytest.skip("live mac tests disabled")
    assert mac_runtime_available() is True
