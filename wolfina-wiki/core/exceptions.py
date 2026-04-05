class WikiError(Exception):
    """Base exception for all application errors."""


class NotFound(WikiError):
    """Resource does not exist."""


class Conflict(WikiError):
    """Operation would create an inconsistent state (e.g. duplicate slug)."""


class InvalidTransition(WikiError):
    """Proposal state machine received an illegal transition."""


class RoleViolation(WikiError):
    """An Agent attempted to occupy more than one governance role on a proposal."""


class PluginError(WikiError):
    """A plugin raised an error; wrapped to prevent leaking into core."""
