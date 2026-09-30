"""Import every model so Alembic and the mapper registry see the full schema."""

from app.models.audit import AuditEvent
from app.models.branch import Branch
from app.models.chunk import Chunk
from app.models.conflict import Conflict
from app.models.contact import Contact
from app.models.department import Department
from app.models.document import Document, DocumentVersion, document_branches
from app.models.feedback import Feedback
from app.models.query_log import AnswerLog, Citation, QueryLog
from app.models.supersession import Supersession
from app.models.user import User

__all__ = [
    "AnswerLog",
    "AuditEvent",
    "Branch",
    "Chunk",
    "Citation",
    "Conflict",
    "Contact",
    "Department",
    "Document",
    "DocumentVersion",
    "Feedback",
    "QueryLog",
    "Supersession",
    "User",
    "document_branches",
]
