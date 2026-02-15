from langfuse import Langfuse

from backend.config import LANGFUSE_SECRET_KEY, LANGFUSE_PUBLIC_KEY, LANGFUSE_HOST

_langfuse: Langfuse | None = None


def get_langfuse() -> Langfuse | None:
    global _langfuse
    if _langfuse is not None:
        return _langfuse

    if not LANGFUSE_SECRET_KEY or not LANGFUSE_PUBLIC_KEY:
        return None

    _langfuse = Langfuse(
        secret_key=LANGFUSE_SECRET_KEY,
        public_key=LANGFUSE_PUBLIC_KEY,
        host=LANGFUSE_HOST,
    )
    return _langfuse
