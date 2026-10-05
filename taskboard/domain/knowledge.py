"""Process knowledge: box kinds and link types (built-in and custom), box keys, extra fields, and
the revision content of boxes, links and controls.

DESIGN Module 3. A process's map is a tree of boxes ("part of") plus typed links between boxes.
Kinds and link types are configurable; the built-in ones carry the behaviour the views rely on
(`role`): steps build the tree and the FMEA path, failure modes have controls, defects form a
department's catalogue and the control plan starts from them, and the `leads_to` link drives the
FMEA chips and the control plan. Every save of a box, link or control is a new revision holding
its full content, so releases (later) and the per-box history work from revisions alone.
"""

import re
import unicodedata
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from taskboard.domain.errors import RuleViolationError

MAX_KEY_LENGTH = 60


class BoxRole(StrEnum):
    """What a kind of box does in the views. Custom kinds are plain."""

    STEP = "step"  # builds the tree; the FMEA shows the steps that lead to failure modes
    KNOWLEDGE = "knowledge"
    REFERENCE = "reference"
    RULE = "rule"
    FAILURE_MODE = "failure_mode"  # has controls; the FMEA's subject
    DEFECT = "defect"  # outside the trees: a department's catalogue; the control plan starts here
    PLAIN = "plain"


class LinkRole(StrEnum):
    LEADS_TO = "leads_to"  # failure mode → defect or failure mode (FMEA chips, control plan)
    PLAIN = "plain"


class ControlKind(StrEnum):
    PREVENT = "prevent"
    DETECT = "detect"


class ExternalLinkKind(StrEnum):
    DASHBOARD = "dashboard"
    GRAPH = "graph"
    CALIBRATION = "calibration"  # calibration diagram
    DOCUMENT = "document"
    WEBSITE = "website"


class ReferenceRole(StrEnum):
    """Why a task or change points at a box (DESIGN principle 5)."""

    AFFECTS = "affects"  # a process change affects this part of the process
    RELATED = "related"  # a task is about it
    ACTION = "action"  # later: an FMEA action carried out as a task


class ObjectType(StrEnum):
    """What a revision is of."""

    BOX = "box"
    LINK = "link"
    CONTROL = "control"


@dataclass(frozen=True, slots=True)
class KindSpec:
    key: str
    name: str
    role: BoxRole
    style: str  # a named palette entry (CSS tokens for light and dark, and an icon)
    description: str
    has_facts: bool = False
    has_main_url: bool = False
    field_schema: tuple[dict[str, Any], ...] = ()


@dataclass(frozen=True, slots=True)
class LinkTypeSpec:
    key: str
    forward_name: str
    backward_name: str
    role: LinkRole
    description: str


# The MapSettings mockup. Keys match the design's sample data.
BUILTIN_KINDS: tuple[KindSpec, ...] = (
    KindSpec(
        "step",
        "Process step",
        BoxRole.STEP,
        "step",
        "A part of the process: tundish, mould, a sub-step.",
    ),
    KindSpec(
        "know",
        "Knowledge",
        BoxRole.KNOWLEDGE,
        "sand",
        "General information: caster overview, how something works.",
        has_facts=True,
    ),
    KindSpec(
        "ref",
        "Reference",
        BoxRole.REFERENCE,
        "blue",
        "Points to a website or document elsewhere, e.g. speeds and grades.",
        has_main_url=True,
    ),
    KindSpec(
        "rule",
        "Rule",
        BoxRole.RULE,
        "violet",
        "A restriction to respect: planning, safety, quality.",
    ),
    KindSpec(
        "fm",
        "Failure mode",
        BoxRole.FAILURE_MODE,
        "peach",
        "Something that can go wrong in a step.",
    ),
    KindSpec(
        "defect",
        "Defect",
        BoxRole.DEFECT,
        "ink",
        "A visible effect on the product. Shared across processes.",
        field_schema=({"key": "group", "label": "Group", "type": "text"},),
    ),
)

BUILTIN_LINK_TYPES: tuple[LinkTypeSpec, ...] = (
    LinkTypeSpec(
        "leads_to",
        "leads to",
        "caused by",
        LinkRole.LEADS_TO,
        "Failure mode → defect, or failure mode → failure mode. Drives the defect view.",
    ),
    LinkTypeSpec(
        "restricts",
        "restricts",
        "restricted by",
        LinkRole.PLAIN,
        "Rule → the step, grade or failure mode it applies to.",
    ),
    LinkTypeSpec(
        "prevents", "prevents", "prevented by", LinkRole.PLAIN, "Rule or control → failure mode."
    ),
    LinkTypeSpec(
        "explains",
        "explains",
        "explained by",
        LinkRole.PLAIN,
        "Knowledge → anything it gives background for.",
    ),
    LinkTypeSpec(
        "documented_in", "documented in", "documents", LinkRole.PLAIN, "Anything → reference."
    ),
    LinkTypeSpec(
        "see_also",
        "see also",
        "see also",
        LinkRole.PLAIN,
        "Loose link when nothing more specific fits.",
    ),
)

# Palette entries a custom kind may use (each has light and dark tokens and an icon).
KIND_STYLES = ("step", "sand", "blue", "violet", "peach", "ink", "green", "rose", "teal", "grey")


# ---------------------------------------------------------------- keys


def slugify(name: str) -> str:
    """`Mould level fluctuation` → `mould-level-fluctuation`; ASCII, at most 60 characters."""
    ascii_name = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode()
    slug = re.sub(r"[^a-z0-9]+", "-", ascii_name.lower()).strip("-")
    return slug[:MAX_KEY_LENGTH].rstrip("-") or "box"


def unique_key(name: str, taken: Iterable[str]) -> str:
    """A box key from its name, made unique with `-2`, `-3`, ... It never changes afterwards."""
    used = set(taken)
    base = slugify(name)
    if base not in used:
        return base
    number = 2
    while True:
        suffix = f"-{number}"
        candidate = f"{base[: MAX_KEY_LENGTH - len(suffix)].rstrip('-')}{suffix}"
        if candidate not in used:
            return candidate
        number += 1


# ---------------------------------------------------------------- extra fields


FIELD_TYPES = ("text", "number")


def check_field_schema(schema: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """Extra fields of a kind or link type (DESIGN principle 1): `[{key, label, type}]`."""
    result: list[dict[str, Any]] = []
    seen: set[str] = set()
    for field in schema:
        key = str(field.get("key", "")).strip()
        label = str(field.get("label", "")).strip() or key
        kind = str(field.get("type", "text"))
        if not re.fullmatch(r"[a-z][a-z0-9_]{0,39}", key):
            raise RuleViolationError(f"a field key is lowercase letters, digits and _: {key!r}")
        if key in seen:
            raise RuleViolationError(f"the field {key} appears twice")
        if kind not in FIELD_TYPES:
            raise RuleViolationError(f"a field is text or number, not {kind}")
        seen.add(key)
        result.append({"key": key, "label": label[:100], "type": kind})
    return result


def check_fields(values: Mapping[str, Any], schema: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
    """Keep the values the schema names, as their type; drop empty ones. Unknown keys are refused
    (a typo would otherwise vanish silently)."""
    types = {str(f["key"]): str(f["type"]) for f in schema}
    unknown = set(values) - set(types)
    if unknown:
        raise RuleViolationError(f"no such field: {', '.join(sorted(unknown))}")
    result: dict[str, Any] = {}
    for key, value in values.items():
        if value is None or value == "":
            continue
        if types[key] == "number":
            if isinstance(value, bool) or not isinstance(value, int | float):
                raise RuleViolationError(f"{key} is a number")
            result[key] = value
        else:
            result[key] = str(value)[:2000]
    return result


def check_facts(facts: Iterable[tuple[str, str]]) -> list[list[str]]:
    """Key facts: an ordered list of `[key, value]` pairs (a table), without empty keys."""
    return [[k.strip()[:200], v.strip()[:500]] for k, v in facts if k.strip()]


def check_url(url: str | None) -> str | None:
    """Only web links (http or https): they open in a new tab, never as script."""
    if url is None or not url.strip():
        return None
    text = url.strip()
    if not re.match(r"https?://[^\s/$.?#].[^\s]*$", text, re.IGNORECASE):
        raise RuleViolationError(f"links must be web addresses (http or https): {text}")
    return text[:2000]


def with_box_param(url: str, box_key: str) -> str:
    """`?node=<box key>` added to an external link, so dashboards can open filtered (DESIGN)."""
    separator = "&" if "?" in url else "?"
    return f"{url}{separator}node={box_key}"


# ---------------------------------------------------------------- order

POSITION_GAP = 1024  # room between neighbours, so most insertions renumber nothing


def stable_positions(current: Sequence[int | None], gap: int = POSITION_GAP) -> list[int]:
    """Positions for items in their wanted order, changing as few existing ones as possible.

    `current` is each item's present position (None for a new item). Every position that can
    stay (the longest run already in increasing order) stays; the others go into the gaps around
    them. Only when a gap is too small is everything renumbered. A position that changes is a
    real edit of that box or control (a new revision), so this keeps revisions meaningful.
    """
    keep = _longest_increasing(current)
    result: list[int | None] = [current[i] if i in keep else None for i in range(len(current))]
    index = 0
    while index < len(result):
        if result[index] is not None:
            index += 1
            continue
        end = index
        while end < len(result) and result[end] is None:
            end += 1
        low: int = (result[index - 1] or 0) if index > 0 else 0  # filled left to right
        high: int | None = result[end] if end < len(result) else None
        count = end - index
        if high is None:
            result[index:end] = [low + gap * (n + 1) for n in range(count)]
        elif high - low > count:
            step = (high - low) / (count + 1)
            result[index:end] = [int(low + step * (n + 1)) for n in range(count)]
        else:
            return [gap * (n + 1) for n in range(len(current))]
        index = end
    return [p or 0 for p in result]


def _longest_increasing(values: Sequence[int | None]) -> set[int]:
    """Indexes of a longest strictly increasing run of the known values (O(n log n))."""
    tails: list[int] = []  # index of the smallest tail of each run length
    previous: dict[int, int | None] = {}
    for i, value in enumerate(values):
        if value is None:
            continue
        lo, hi = 0, len(tails)
        while lo < hi:
            mid = (lo + hi) // 2
            if (values[tails[mid]] or 0) < value:
                lo = mid + 1
            else:
                hi = mid
        previous[i] = tails[lo - 1] if lo > 0 else None
        if lo == len(tails):
            tails.append(i)
        else:
            tails[lo] = i
    chosen: set[int] = set()
    at = tails[-1] if tails else None
    while at is not None:
        chosen.add(at)
        at = previous[at]
    return chosen


# ---------------------------------------------------------------- revisions


def changed_fields(before: Mapping[str, Any] | None, after: Mapping[str, Any]) -> list[str]:
    """Which top-level fields differ between two revisions' content (for the history)."""
    if before is None:
        return []
    return sorted(k for k in set(before) | set(after) if before.get(k) != after.get(k))
