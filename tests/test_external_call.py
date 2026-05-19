import time

from app.services.external_call import call_with_timeout


def test_call_with_timeout_returns_value():
    assert call_with_timeout(lambda: 42, 5) == 42


def test_call_with_timeout_on_slow_call():
    def slow():
        time.sleep(2)
        return 1

    assert call_with_timeout(slow, 0.1) is None
