"""The daily check that compares Vapi's call list with what reached GHL."""
import json

from receptionist.reconcile import exit_code, main, reconcile


def test_finds_a_call_the_webhook_never_received(h):
    h.report("call_demo_0001")
    calls = [{"id": "call_demo_0001", "status": "ended"}, {"id": "call_demo_0002", "status": "ended"},
             {"id": "call_demo_0003", "status": "in-progress"}]
    report = reconcile(h.store, calls)
    assert report["missing"] == ["call_demo_0002"]
    assert exit_code(report) == 1


def test_clean_window_exits_zero(h):
    h.report("call_demo_0001")
    report = reconcile(h.store, [{"id": "call_demo_0001", "status": "ended"}])
    assert report["missing"] == [] and report["unfinished"] == [] and exit_code(report) == 0


def test_a_full_page_is_never_called_clean(h):
    h.report("call_demo_0001")
    report = reconcile(h.store, [{"id": "call_demo_0001", "status": "ended"}], limit=1)
    assert report["truncated"] and exit_code(report) == 2


def test_unfinished_and_unclear_writes_are_reported(h):
    h.ghl_fake.fail("send_sms", "timeout_after_write")
    h.report("call_demo_0001")
    report = reconcile(h.store, [{"id": "call_demo_0001", "status": "ended"}])
    assert report["unfinished"][0]["status"] == "needs_check"
    assert report["unclear"][0]["step"] == "owner_summary"


def test_cli_reads_an_exported_call_list(h, tmp_path, capsys):
    calls = tmp_path / "calls.json"
    calls.write_text(json.dumps([{"id": "call_demo_0009", "status": "ended"}]))
    assert main(["--calls", str(calls), "--db", h.settings.db_path]) == 1
    assert "call_demo_0009" in capsys.readouterr().out
