"""The agent guide's generated part: short types from OpenAPI schemas, and the endpoint list."""

from taskboard.services.agent_guide import agent_guide, endpoint_list, type_text

SPEC = {
    "components": {
        "schemas": {
            "TaskStatus": {"type": "string", "enum": ["idea", "started", "done", "archived"]},
            "Placement": {"type": "object", "properties": {"project_id": {"type": "integer"}}},
            "TaskCreate": {
                "type": "object",
                "required": ["title"],
                "properties": {
                    "title": {"type": "string", "maxLength": 300},
                    "status": {"$ref": "#/components/schemas/TaskStatus"},
                    "helper_ids": {"type": "array", "items": {"type": "integer"}},
                    "placements": {
                        "type": "array",
                        "items": {"$ref": "#/components/schemas/Placement"},
                    },
                    "due": {"anyOf": [{"type": "string", "format": "date"}, {"type": "null"}]},
                },
            },
        }
    },
    "paths": {
        "/api/tasks": {
            "get": {
                "tags": ["tasks"],
                "summary": "List Tasks",
                "description": "Visible tasks in rank order.\n\nMore detail.",
                "parameters": [
                    {"name": "q", "in": "query", "schema": {"type": "string"}},
                    {"name": "key", "in": "path", "required": True, "schema": {"type": "string"}},
                ],
            },
            "post": {
                "tags": ["tasks"],
                "summary": "Create Task",
                "requestBody": {
                    "content": {
                        "application/json": {"schema": {"$ref": "#/components/schemas/TaskCreate"}}
                    }
                },
            },
        },
        "/api/auth/me": {"get": {"tags": ["auth"], "summary": "Me"}},
        "/api/auth/login": {"post": {"tags": ["auth"], "summary": "Login"}},
        "/api/admin/users": {"get": {"tags": ["administration"], "summary": "List Users"}},
        "/api/tasks/{key}/attachments": {
            "post": {
                "tags": ["conversation"],
                "summary": "Upload",
                "requestBody": {"content": {"multipart/form-data": {"schema": {}}}},
            }
        },
    },
}


def test_short_types() -> None:
    props = SPEC["components"]["schemas"]["TaskCreate"]["properties"]
    assert type_text(SPEC, props["title"]) == "string"
    assert type_text(SPEC, props["status"]) == "idea|started|done|archived"
    assert type_text(SPEC, props["helper_ids"]) == "(integer)[]"
    assert type_text(SPEC, props["placements"]) == "(Placement)[]"
    assert type_text(SPEC, props["due"]) == "date|null"
    assert type_text(SPEC, {}) == "any"


def test_the_endpoint_list() -> None:
    text = endpoint_list(SPEC)
    assert text.splitlines() == [
        "### Tasks",
        "",
        "- `GET /api/tasks`: Visible tasks in rank order.",
        "  - query: `q` string",
        "- `POST /api/tasks`: Create Task",
        "  - body: `title`* string, `status` idea|started|done|archived, `helper_ids` (integer)[],"
        " `placements` (Placement)[], `due` date|null",
        "",
        "### Auth",
        "",
        "- `GET /api/auth/me`: Me",
        "",
        "### Conversation",
        "",
        "- `POST /api/tasks/{key}/attachments`: Upload",
        "  - body: a file upload (multipart/form-data, field `file`)",
    ]


def test_the_guide_fills_in_the_address() -> None:
    guide = agent_guide(SPEC, base_url="https://tasks.example.com/tb/")
    assert "https://tasks.example.com/tb/api/auth/me" in guide
    assert "https://tasks.example.com/tb/profile" in guide
    assert "{{" not in guide and "### Tasks" in guide
