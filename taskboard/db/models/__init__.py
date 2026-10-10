"""All tables. Importing this package registers every model on `Base.metadata`."""

from taskboard.db.base import Base
from taskboard.db.models.changes import Change, ChangePeriod
from taskboard.db.models.conversation import Attachment, Event, Post, PostRevision
from taskboard.db.models.identity import (
    ApiToken,
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
from taskboard.db.models.knowledge import (
    Box,
    BoxKind,
    BoxLink,
    Control,
    ExternalLink,
    LinkType,
    Reference,
    Release,
    ReleaseItem,
    Revision,
)
from taskboard.db.models.org import Department, Process, Section
from taskboard.db.models.people import Person
from taskboard.db.models.projects import Project, ProjectNode
from taskboard.db.models.system import AppLock, BackupSettings
from taskboard.db.models.tasks import Placement, Task, TaskHelper

__all__ = [
    "ApiToken",
    "AppLock",
    "Attachment",
    "AuditEntry",
    "BackupSettings",
    "Base",
    "Box",
    "BoxKind",
    "BoxLink",
    "Change",
    "ChangePeriod",
    "Control",
    "Department",
    "Event",
    "ExternalIdentity",
    "ExternalLink",
    "GroupRoleMapping",
    "LinkType",
    "LoginAttempt",
    "Person",
    "Placement",
    "Post",
    "PostRevision",
    "Process",
    "Project",
    "ProjectNode",
    "Reference",
    "Release",
    "ReleaseItem",
    "Revision",
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
