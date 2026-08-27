"""Teacher-owned classroom analytics and immutable content review."""

from .routes import create_teacher_router
from .service import TeacherService

__all__ = ["TeacherService", "create_teacher_router"]
