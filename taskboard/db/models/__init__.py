"""All tables. Importing this package registers every model on `Base.metadata`."""

from taskboard.db.base import Base
from taskboard.db.models.conversation import Attachment, Event, Post
from taskboard.db.models.identity import (
    AuditEntry,
    ExternalIdentity,
    GroupRoleMapping,
    LoginAttempt,
    Role,
    RoleAssignment,
    RolePermission,
    SsoRequest,
    User,
    UserSession,
)
from taskboard.db.models.org import Department, Section
from taskboard.db.models.people import Person
from taskboard.db.models.projects import Project, ProjectNode
from taskboard.db.models.system import AppLock
from taskboard.db.models.tasks import Placement, Task, TaskHelper

__all__ = [
    "AppLock",
    "Attachment",
    "AuditEntry",
    "Base",
    "Department",
    "Event",
    "ExternalIdentity",
    "GroupRoleMapping",
    "LoginAttempt",
    "Person",
    "Placement",
    "Post",
    "Project",
    "ProjectNode",
    "Role",
    "RoleAssignment",
    "RolePermission",
    "Section",
    "SsoRequest",
    "Task",
    "TaskHelper",
    "User",
    "UserSession",
]
