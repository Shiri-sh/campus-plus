"""Failures a command can hand back to a route."""


class CommandError(Exception):
    """A business rule rejected the write. ``message`` is safe to flash."""

    def __init__(self, message):
        super().__init__(message)
        self.message = message


class NotFound(CommandError):
    """The target row does not exist. Routes turn this into HTTP 404."""

    def __init__(self):
        super().__init__("not found")
