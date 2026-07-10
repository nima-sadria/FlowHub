"""Tests for database-backed authentication throttling."""

from __future__ import annotations

from datetime import datetime, timedelta

from sqlalchemy.orm import sessionmaker

from app.flowhub.auth.rate_limiter import WINDOW, clear_login_attempts, consume_login_attempt


class TestRateLimiter:
    def test_first_request_allowed(self, db):
        assert consume_login_attempt(db, "1.2.3.4") is True

    def test_fifth_attempt_is_allowed_and_sixth_is_blocked(self, db):
        for _ in range(5):
            assert consume_login_attempt(db, "1.2.3.4") is True
        assert consume_login_attempt(db, "1.2.3.4") is False

    def test_window_expiry_allows_a_new_attempt(self, db):
        now = datetime(2026, 1, 1, 0, 0, 0)
        for _ in range(5):
            assert consume_login_attempt(db, "1.2.3.4", now=now) is True
        assert consume_login_attempt(db, "1.2.3.4", now=now) is False
        assert consume_login_attempt(db, "1.2.3.4", now=now + WINDOW + timedelta(seconds=1)) is True

    def test_different_ips_are_independent(self, db):
        for _ in range(5):
            assert consume_login_attempt(db, "1.2.3.4") is True
        assert consume_login_attempt(db, "1.2.3.4") is False
        assert consume_login_attempt(db, "5.6.7.8") is True

    def test_state_is_shared_across_database_sessions(self, db):
        Session = sessionmaker(bind=db.get_bind())
        second = Session()
        try:
            for _ in range(4):
                assert consume_login_attempt(db, "1.2.3.4") is True
            assert consume_login_attempt(second, "1.2.3.4") is True
            assert consume_login_attempt(db, "1.2.3.4") is False
        finally:
            second.close()

    def test_successful_login_reset_clears_attempts(self, db):
        for _ in range(5):
            assert consume_login_attempt(db, "1.2.3.4") is True
        clear_login_attempts(db, "1.2.3.4")
        assert consume_login_attempt(db, "1.2.3.4") is True
