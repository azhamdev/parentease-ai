import os
from langfuse import Langfuse
import logging

logger = logging.getLogger(__name__)

langfuse_client: Langfuse | None = None

def init_langfuse() -> Langfuse | None:
    """
    Inisialisasi Langfuse client (Compatible with v3+).
    Dipanggil saat startup aplikasi.
    """
    global langfuse_client
    public_key = os.getenv("LANGFUSE_PUBLIC_KEY")
    secret_key = os.getenv("LANGFUSE_SECRET_KEY")
    host = (
        os.getenv("LANGFUSE_HOST")
        or os.getenv("LANGFUSE_BASE_URL")
        or "https://cloud.langfuse.com"
    )

    if not public_key or not secret_key:
        message = "Langfuse credentials not found. Tracing disabled."
        logger.warning(message)
        print(f"⚠️ {message}")
        return None

    try:
        # ✅ INIT v3: Instance Langfuse sekarang sebagai config manager
        langfuse_client = Langfuse(
            public_key=public_key,
            secret_key=secret_key,
            host=host,
            release="1.0.0",  # Opsional: versioning untuk trace
        )
        message = f"Langfuse initialized successfully: {host}"
        logger.info(message)
        print(f"✅ {message}")
        return langfuse_client
    except Exception as e:
        logger.error(f"Failed to initialize Langfuse: {e}")
        print(f"❌ Failed to initialize Langfuse: {e}")
        return None
