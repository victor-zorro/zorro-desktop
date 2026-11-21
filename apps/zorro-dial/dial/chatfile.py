"""The conversation shared with Intelligence: the code is apps/zorro-fx/zorro_chat.py."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'zorro-fx'))
from zorro_chat import (SEND_LIMIT, append, for_engine, load, message, new_chat,  # noqa: E402,F401
                        path, write)
