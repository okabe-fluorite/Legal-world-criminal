from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from src.core.database import Base, create_database_engine, create_session_factory, get_db_session
from src.core.models import Sandbox, User
from src.core.sandbox_service import SandboxService


class SandboxConcurrencyTests(unittest.TestCase):
    def test_new_sandbox_releases_database_lock_before_seed_io(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            engine = create_database_engine(
                f"sqlite+pysqlite:///{(root / 'runtime.db').as_posix()}"
            )
            Base.metadata.create_all(engine)
            factory = create_session_factory(engine)
            with get_db_session(factory) as session:
                session.add_all(
                    [
                        User(id="student-a", email="a@example.com"),
                        User(id="student-b", email="b@example.com"),
                    ]
                )

            class ProbingSandboxService(SandboxService):
                def _initialize_seed_storage(self, storage_root: Path) -> None:
                    # A second request must be able to write while the first
                    # request performs filesystem-heavy seed initialization.
                    with get_db_session(factory) as other:
                        other.add(
                            Sandbox(
                                id="sandbox-b",
                                user_id="student-b",
                                sandbox_key="probe-b",
                                status="idle",
                                storage_root=str(root / "student-b"),
                            )
                        )
                        other.flush()
                    storage_root.mkdir(parents=True, exist_ok=True)

            service = ProbingSandboxService(base_dir=root / "sandboxes")
            with get_db_session(factory) as session:
                first = service.get_or_create_user_sandbox(
                    session=session, user_id="student-a"
                )
                self.assertEqual(first.user_id, "student-a")

            with get_db_session(factory) as session:
                self.assertIsNotNone(session.get(Sandbox, "sandbox-b"))
                self.assertIsNotNone(
                    service.get_user_sandbox(session=session, user_id="student-a")
                )
            engine.dispose()


if __name__ == "__main__":
    unittest.main()
