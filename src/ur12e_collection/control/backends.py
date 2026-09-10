"""Explicit connection factories; hardware motion has no enabled entrypoint."""

from ur12e_collection.control.model import ControlError


def open_backend(backend: str):
    """Reject physical control before importing an SDK or opening any socket."""
    if backend != "ursim":
        raise ControlError(
            "physical control is disabled; only URSim is authorized"
        )
    # pylint: disable-next=import-outside-toplevel
    from ur12e_collection.simulation import connection

    return connection.open_controller()
