import pytest

from cognitiveio.config import Settings
from cognitiveio.demo.demo_runner import run_demo


@pytest.mark.asyncio
async def test_demo_includes_conflict_and_trust_circuit(tmp_path):
    settings = Settings(app_home=tmp_path)
    result = await run_demo(settings)

    episodes = {item["name"]: item for item in result["episodes"]}
    assert episodes["Candidate conflict guard in email profile"]["actual"] == "do_nothing"
    assert episodes["Trust signal 1 - accept then undo"]["actual"] == "undo"
    assert episodes["Trust signal 2 - dismissal"]["actual"] == "dismiss"
    assert episodes["Trust circuit breaker cooldown"]["actual"] == "do_nothing"
    assert "trust cooldown" in episodes["Trust circuit breaker cooldown"]["message"].lower()

    report = result["report"].to_dict()
    assert int(report.get("blocked_candidate_conflict", 0)) >= 1
    assert int(report.get("blocked_trust_circuit", 0)) >= 1
