import os

import pytest

os.environ.setdefault("OAUPA_MASTER_KEY", "MDEyMzQ1Njc4OWFiY2RlZjAxMjM0NTY3ODlhYmNkZWY=")

from app.core.encryption import decrypt, encrypt, get_current_key_version


class TestEncryption:
    def test_encrypt_decrypt_roundtrip(self):
        plaintext = "ya29.a0ARrdaM8_access_token_here"
        blob = encrypt(plaintext)
        assert decrypt(blob) == plaintext

    def test_encrypt_decrypt_empty(self):
        blob = encrypt("")
        assert decrypt(blob) == ""

    def test_encrypt_decrypt_unicode(self):
        plaintext = "토큰값-テスト-🔑"
        blob = encrypt(plaintext)
        assert decrypt(blob) == plaintext

    def test_encrypt_decrypt_long_string(self):
        plaintext = "x" * 10000
        blob = encrypt(plaintext)
        assert decrypt(blob) == plaintext

    def test_different_blobs_for_same_plaintext(self):
        blob1 = encrypt("same-token")
        blob2 = encrypt("same-token")
        assert blob1 != blob2  # random DEK + nonce

    def test_corrupted_blob_raises(self):
        blob = encrypt("test")
        corrupted = blob[:-1] + bytes([blob[-1] ^ 0xFF])
        with pytest.raises(Exception):
            decrypt(corrupted)

    def test_truncated_blob_raises(self):
        blob = encrypt("test")
        with pytest.raises(Exception):
            decrypt(blob[:10])

    def test_get_current_key_version(self):
        assert get_current_key_version() == "v1"

    def test_missing_master_key(self):
        from unittest.mock import patch
        with patch("app.core.encryption.settings") as mock_settings:
            mock_settings.oaupa_master_key = ""
            with pytest.raises(RuntimeError, match="not set"):
                encrypt("test")

    def test_wrong_length_master_key(self):
        import base64
        from unittest.mock import patch
        with patch("app.core.encryption.settings") as mock_settings:
            mock_settings.oaupa_master_key = base64.b64encode(b"short").decode()
            with pytest.raises(RuntimeError, match="32 bytes"):
                encrypt("test")
