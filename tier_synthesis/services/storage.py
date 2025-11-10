import os
import hashlib
import hmac
import time
from urllib.parse import urlencode
import logging

logger = logging.getLogger(__name__)


def is_local_dev():
    return os.environ.get("LOCAL_DEV", "false").lower() == "true"


class StorageService:
    def __init__(self):
        self.storage_path = os.environ.get("STORAGE_PATH", "app/uploads")
        self.signing_secret = self._get_signing_secret()

        os.makedirs(os.path.join(self.storage_path, "thumbnails"), exist_ok=True)
        os.makedirs(os.path.join(self.storage_path, "full"), exist_ok=True)

    def _get_signing_secret(self) -> str:
        secret = os.environ.get("URL_SIGNING_SECRET")
        if secret:
            return secret

        if is_local_dev():
            return "dev-secret-do-not-use-in-production"

        raise RuntimeError(
            "URL_SIGNING_SECRET environment variable required in production. "
            "Generate with: openssl rand -hex 32"
        )

    def generate_file_path(self, image_id: int, content_type: str, is_thumbnail: bool = False) -> str:
        ext = content_type.split("/")[1] if "/" in content_type else "jpg"
        id_hash = hashlib.md5(str(image_id).encode()).hexdigest()[:2]
        filename_hash = hashlib.sha256(
            f"{image_id}{self.signing_secret}".encode()
        ).hexdigest()[:16]

        prefix = "thumbnails" if is_thumbnail else "full"
        return f"{prefix}/{id_hash}/{image_id}_{filename_hash}.{ext}"

    def save_image(self, image_data: bytes, image_id: int, content_type: str, is_thumbnail: bool = False) -> str:
        file_path = self.generate_file_path(image_id, content_type, is_thumbnail)
        full_path = os.path.join(self.storage_path, file_path)

        os.makedirs(os.path.dirname(full_path), exist_ok=True)
        with open(full_path, "wb") as f:
            f.write(image_data)

        logger.info(f"Saved image: {file_path} ({len(image_data)} bytes)")
        return file_path

    def delete_image(self, file_path: str) -> bool:
        if not file_path:
            return False

        try:
            full_path = os.path.join(self.storage_path, file_path)
            if os.path.exists(full_path):
                os.remove(full_path)
                logger.info(f"Deleted: {file_path}")
                return True
        except Exception as e:
            logger.error(f"Failed to delete {file_path}: {e}")

        return False

    def read_image(self, file_path: str) -> bytes | None:
        if not file_path:
            return None

        full_path = os.path.join(self.storage_path, file_path)
        if not os.path.exists(full_path):
            logger.warning(f"File not found: {file_path}")
            return None

        with open(full_path, "rb") as f:
            return f.read()

    def generate_signed_url(self, file_path: str, cache_bust: bool = False) -> str:
        """Generate signed URL with daily expiry for optimal caching.

        URLs expire at midnight UTC (next day), meaning:
        - Same URL for all users/renders within a day
        - Maximum browser caching efficiency
        - Access re-validated daily at page render
        - Simple and efficient

        Args:
            file_path: Path to the file
            cache_bust: If True, append timestamp to force browser cache invalidation
        """
        current_time = int(time.time())
        seconds_per_day = 86400
        expiry = ((current_time // seconds_per_day) + 1) * seconds_per_day

        message = f"{file_path}:{expiry}"
        signature = hmac.new(
            self.signing_secret.encode(),
            message.encode(),
            hashlib.sha256
        ).hexdigest()

        params = urlencode({"path": file_path, "expires": expiry, "sig": signature})
        url = f"/images/img?{params}"

        if cache_bust:
            url = f"{url}&t={current_time}"

        return url

    def validate_signature(self, file_path: str, expiry: int, signature: str) -> bool:
        if int(time.time()) > expiry:
            logger.warning(f"Expired URL for {file_path}")
            return False

        message = f"{file_path}:{expiry}"
        expected = hmac.new(
            self.signing_secret.encode(),
            message.encode(),
            hashlib.sha256
        ).hexdigest()

        if not hmac.compare_digest(signature, expected):
            logger.warning(f"Invalid signature for {file_path}")
            return False

        return True


_storage_service: StorageService | None = None


def get_storage_service() -> StorageService:
    global _storage_service
    if _storage_service is None:
        _storage_service = StorageService()
    return _storage_service
