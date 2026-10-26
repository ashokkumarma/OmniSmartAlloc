from demo import server


def test_scheduled_agent_runs_only_changed_sku(monkeypatch):
    calls = []

    class FakeTimer:
        def __init__(self, delay, fn):
            self.fn = fn

        def start(self):
            pass

        def cancel(self):
            pass

        def is_alive(self):
            return False

    class FakeThread:
        def __init__(self, target, args=(), daemon=None):
            self.target, self.args = target, args

        def start(self):
            self.target(*self.args)

    monkeypatch.setattr(server.threading, "Timer", FakeTimer)
    monkeypatch.setattr(server.threading, "Thread", FakeThread)
    monkeypatch.setattr(server, "_run_agent", lambda scopes: calls.append(scopes))
    monkeypatch.setitem(server._AUTO_AGENT, "enabled", True)
    monkeypatch.setitem(server._AGENT_JOB, "running", False)
    monkeypatch.setattr(server, "_AGENT_PENDING_ALL", False)
    monkeypatch.setattr(server, "_AGENT_PENDING_SKUS", set())
    monkeypatch.setattr(server, "_AGENT_TIMER", None)

    server._schedule_agent_run("LOCK-004")
    server._kick_scheduled_agent()

    assert calls == [["LOCK-004"]]


def test_debounced_fulfillments_queue_only_their_skus(monkeypatch):
    calls = []

    class FakeTimer:
        def __init__(self, delay, fn):
            self.fn = fn

        def start(self):
            pass

        def cancel(self):
            pass

        def is_alive(self):
            return False

    class FakeThread:
        def __init__(self, target, args=(), daemon=None):
            self.target, self.args = target, args

        def start(self):
            self.target(*self.args)

    monkeypatch.setattr(server.threading, "Timer", FakeTimer)
    monkeypatch.setattr(server.threading, "Thread", FakeThread)
    monkeypatch.setattr(server, "_run_agent", lambda scopes: calls.append(scopes))
    monkeypatch.setitem(server._AUTO_AGENT, "enabled", True)
    monkeypatch.setitem(server._AGENT_JOB, "running", False)
    monkeypatch.setattr(server, "_AGENT_PENDING_ALL", False)
    monkeypatch.setattr(server, "_AGENT_PENDING_SKUS", set())
    monkeypatch.setattr(server, "_AGENT_TIMER", None)

    server._schedule_agent_run("LAMP-002")
    server._schedule_agent_run("LOCK-004")
    server._kick_scheduled_agent()

    assert calls == [["LAMP-002", "LOCK-004"]]
