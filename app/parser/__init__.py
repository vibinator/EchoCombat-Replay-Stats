"""Echo VR replay parser. No database or web imports."""

from .errors import CorruptReplay, IncompleteReplay, ReplayError, UnsupportedReplay
from .models import Frame, PayloadState, PlayerFrame, ReplayMeta
from .reader import ParsedReplay, open_replay

PARSER_VERSION = "3"

__all__ = [
    "PARSER_VERSION",
    "CorruptReplay",
    "Frame",
    "IncompleteReplay",
    "ParsedReplay",
    "PayloadState",
    "PlayerFrame",
    "ReplayError",
    "ReplayMeta",
    "UnsupportedReplay",
    "open_replay",
]
