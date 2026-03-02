import os

import pytest

from cognitiveio.ai.fm_arbiter import Candidate, decide_with_apple_fm


@pytest.mark.live_fm
@pytest.mark.asyncio
async def test_fm_selector_only_live():
    if os.getenv("COGNITIVEIO_ENABLE_LIVE_FM_TESTS", "0") != "1":
        pytest.skip("live FM tests disabled")

    decision = await decide_with_apple_fm(
        packet={"profile": "email_docs", "context": {"token": "api"}},
        candidates=[
            Candidate(id="c1", before="api", after="Application Programming Interface", count=3, confidence=0.9),
            Candidate(id="c2", before="api", after="api", count=1, confidence=0.5),
        ],
        timeout_seconds=0.2,
    )
    assert decision.action in {"do_nothing", "suggest", "auto_apply"}
    assert decision.chosen_candidate_id in {"c1", "c2", None}
