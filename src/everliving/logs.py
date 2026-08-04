"""One log file for the whole run.

A playtest that fails silently teaches nothing. The 401 that blocked H-1 twice was
only ever visible as a red string in a browser tab — the process itself left nothing
behind, because stdout is buffered when it isn't attached to a terminal. Anything
worth troubleshooting later has to be written down while it happens.

Two rules this module exists to enforce:

- **UTF-8, always.** The default encoding on Windows is cp950, which cannot encode
  陌洲. A log that crashes on the narrative is worse than no log.
- **Never the API key.** Nothing here formats an environment variable. Message
  content is the player's, so it only lands in the file at DEBUG.
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path

LOG_FILENAME = "everliving.log"
_LOGGER_NAME = "everliving"
_FORMAT = "%(asctime)s %(levelname)-7s %(name)s | %(message)s"


def setup(
    path: str | Path = LOG_FILENAME,
    level: int = logging.INFO,
    console: bool = True,
) -> Path:
    """Point the `everliving` logger at a file, replacing any earlier setup."""
    logger = logging.getLogger(_LOGGER_NAME)
    logger.setLevel(level)
    # Ours alone: the root logger's handlers are the host application's business.
    logger.propagate = False
    _clear(logger)

    log_path = Path(path)
    handler = logging.FileHandler(log_path, encoding="utf-8")
    handler.setFormatter(logging.Formatter(_FORMAT))
    logger.addHandler(handler)

    if console:
        # stderr, not stdout: unbuffered, and it keeps the log out of anything that
        # pipes the program's normal output somewhere.
        stream = logging.StreamHandler(sys.stderr)
        stream.setFormatter(logging.Formatter(_FORMAT))
        logger.addHandler(stream)

    return log_path


def reset() -> None:
    """Drop every handler, closing files. Mostly for tests and for a clean exit."""
    _clear(logging.getLogger(_LOGGER_NAME))


def _clear(logger: logging.Logger) -> None:
    """Setup runs more than once in a process (CLI then web, or test after test);
    leaving the old handlers attached would write every line twice."""
    for handler in list(logger.handlers):
        logger.removeHandler(handler)
        handler.close()


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(f"{_LOGGER_NAME}.{name}")
