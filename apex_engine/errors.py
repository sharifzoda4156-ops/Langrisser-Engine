class EngineError(ValueError):
    """A rejected request; no match mutation is committed."""


class Conflict(EngineError):
    """Stale state or conflicting reuse of a decision request."""


class NotFound(EngineError):
    """Requested match does not exist."""
