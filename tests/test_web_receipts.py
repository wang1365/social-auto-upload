from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from utils.publish_receipt import attempted, confirmed, stop_web_resubmission


def test_confirmation_storage_failure_cannot_trigger_platform_resubmission():
    uploader = Mock()
    uploader.on_publish_confirmed.side_effect = RuntimeError("storage unavailable")
    confirmed(uploader)
    assert uploader.publish_confirmed is True


def test_uncertain_web_submission_stops_before_a_second_click():
    uploader = SimpleNamespace(on_publish_attempt=lambda: None)
    clicks = 0
    with pytest.raises(RuntimeError, match="核实"):
        for _ in range(3):
            try:
                attempted(uploader)
                clicks += 1
                raise TimeoutError("platform navigation timed out")
            except TimeoutError:
                stop_web_resubmission(uploader)
    assert clicks == 1


def test_cli_submit_retry_behavior_is_preserved():
    uploader = SimpleNamespace()
    attempted(uploader)
    stop_web_resubmission(uploader)
