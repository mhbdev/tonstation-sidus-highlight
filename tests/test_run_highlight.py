from types import SimpleNamespace

import pytest

from tonstation import run_highlight


def test_run_highlight_main(monkeypatch):
    calls = []

    def _fake_build(send=True, target_chat_id=None):
        calls.append((send, target_chat_id))
        return "ok"

    monkeypatch.setattr(run_highlight, "build_and_optionally_send", _fake_build)
    import sys

    monkeypatch.setattr(sys, "argv", ["prog", "--print-only"])
    run_highlight.main()
    assert calls[0] == (False, None)

    monkeypatch.setattr(sys, "argv", ["prog", "--target", "tgt"])
    run_highlight.main()
    assert calls[-1] == (True, "tgt")


def test_run_highlight_guard(monkeypatch):
    import runpy
    import sys
    import tonstation.digest_builder as db
    monkeypatch.setattr(sys, "argv", ["prog", "--print-only"])
    monkeypatch.setattr(db, "build_and_optionally_send", lambda *a, **k: "ok")
    runpy.run_module("tonstation.run_highlight", run_name="__main__", alter_sys=True)
