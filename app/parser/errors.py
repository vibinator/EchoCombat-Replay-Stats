class ReplayError(Exception):
    """Base for replay files that cannot be turned into a match. `code` is stored as replays.error_code."""

    code = "internal"


class UnsupportedReplay(ReplayError):
    code = "unsupported"


class CorruptReplay(ReplayError):
    code = "corrupt"


class IncompleteReplay(ReplayError):
    code = "incomplete"
