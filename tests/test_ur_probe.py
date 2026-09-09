"""Check the read-only allowlist and bounded connection failures."""

from unittest import mock

from ur12e_collection import ur


def test_dashboard_only_sends_read_queries():
    """The probe cannot send play, load, power, or protective-stop commands."""
    connection = mock.MagicMock()
    connection.makefile.return_value.__enter__.return_value.readline.return_value = (
        b"OK\n"
    )
    with mock.patch("socket.create_connection") as connect:
        connect.return_value.__enter__.return_value = connection
        report = ur.dashboard("fixture")
    sent = [call.args[0] for call in connection.sendall.call_args_list]
    assert sent == [(query + "\n").encode() for query in ur.DASHBOARD_QUERIES]
    assert report["state"] == "available"
    connect.assert_called_once_with(("fixture", 29999), timeout=2)
    connection.settimeout.assert_called_once_with(2)


def test_dashboard_connection_failure_is_reported():
    """An unavailable controller cannot appear as a valid identity."""
    with mock.patch(
        "socket.create_connection", side_effect=TimeoutError("offline")
    ):
        report = ur.dashboard("fixture")
    assert report["state"] == "failed"
    assert report["responses"] == {}


def test_probe_requires_new_output(tmp_path):
    """A repeated probe never overwrites earlier evidence or contacts devices."""
    existing = tmp_path / "ur.json"
    existing.write_text("previous")
    with mock.patch.object(ur, "dashboard") as dashboard:
        try:
            ur.probe("fixture", 1, existing)
        except FileExistsError:
            pass
        else:
            raise AssertionError("existing report must be preserved")
        dashboard.assert_not_called()
    assert existing.read_text() == "previous"
