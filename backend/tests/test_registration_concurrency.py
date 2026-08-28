from __future__ import annotations

import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Barrier

from sqlalchemy import func, select

from src.core.database import Base, create_database_engine, create_session_factory, get_db_session
from src.core.models import User
from src.core.user_service import register_user


class RegistrationConcurrencyTests(unittest.TestCase):
    def test_four_sqlite_registrations_can_start_together(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            database_path = (Path(temp) / "concurrent-registration.db").as_posix()
            engine = create_database_engine(f"sqlite+pysqlite:///{database_path}")
            Base.metadata.create_all(engine)
            factory = create_session_factory(engine)
            barrier = Barrier(4)

            def create(index: int) -> str:
                barrier.wait(timeout=5)
                with get_db_session(factory) as session:
                    user = register_user(
                        session=session,
                        email=f"concurrent-{index}@example.com",
                        password="Concurrent-Password-2026!",
                    )
                    return str(user.id)

            with ThreadPoolExecutor(max_workers=4) as executor:
                user_ids = list(executor.map(create, (1, 2, 3, 4)))
            self.assertEqual(len(set(user_ids)), 4)
            with get_db_session(factory) as session:
                count = session.scalar(select(func.count()).select_from(User))
            self.assertEqual(count, 4)
            engine.dispose()


if __name__ == "__main__":
    unittest.main()
