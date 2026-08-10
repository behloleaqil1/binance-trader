"""Password-hashing and login-throttle unit tests (session lifecycle is
exercised against the running app in the smoke test)."""
import time

from app import auth


class TestPasswordHashing:
    def test_roundtrip(self):
        salt = "ab" * 16
        h = auth.hash_password("correct horse battery staple", salt)
        assert auth.verify_password("correct horse battery staple", salt, h)

    def test_wrong_password_rejected(self):
        salt = "ab" * 16
        h = auth.hash_password("right", salt)
        assert not auth.verify_password("wrong", salt, h)
        assert not auth.verify_password("", salt, h)

    def test_salt_changes_hash(self):
        assert (auth.hash_password("pw", "aa" * 16)
                != auth.hash_password("pw", "bb" * 16))

    def test_hash_is_not_plaintext(self):
        h = auth.hash_password("hunter22", "cd" * 16)
        assert "hunter22" not in h and len(h) == 64  # sha256 hex


class TestThrottle:
    def test_locks_after_repeated_failures(self):
        ip = "10.9.9.9"
        auth._failed.pop(ip, None)
        for _ in range(auth._LOCK_AFTER):
            auth._record_failure(ip)
        assert auth._locked(ip) > 0

    def test_old_failures_expire(self):
        ip = "10.9.9.8"
        auth._failed[ip] = [time.monotonic() - auth._LOCK_WINDOW - 1] * 10
        assert auth._locked(ip) == 0.0
