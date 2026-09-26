"""Project trees: outline numbers (1, 1.1, 2.2.1), pre-order listing, subtrees and cycle checks.

Nodes are given as plain `TreeNode` values (id, parent, position among siblings). Numbers are
derived from the sibling order and are never stored, so reordering renumbers automatically.
"""

from collections import defaultdict
from collections.abc import Hashable, Iterable
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class TreeNode[K: Hashable]:
    id: K
    parent_id: K | None
    position: int


class Outline[K: Hashable]:
    """An immutable view of one project's node tree."""

    def __init__(self, nodes: Iterable[TreeNode[K]]) -> None:
        self._nodes: dict[K, TreeNode[K]] = {n.id: n for n in nodes}
        children: defaultdict[K | None, list[TreeNode[K]]] = defaultdict(list)
        for node in self._nodes.values():
            children[node.parent_id].append(node)
        self._children: dict[K | None, list[K]] = {
            parent: [n.id for n in sorted(kids, key=lambda n: (n.position, str(n.id)))]
            for parent, kids in children.items()
        }
        self._numbers: dict[K, str] = {}
        self._preorder: list[K] = []
        self._walk(None, "")

    def _walk(self, parent: K | None, prefix: str) -> None:
        for index, child in enumerate(self._children.get(parent, []), start=1):
            number = f"{prefix}{index}"
            self._numbers[child] = number
            self._preorder.append(child)
            self._walk(child, f"{number}.")

    def __contains__(self, node_id: object) -> bool:
        return node_id in self._nodes

    def number(self, node_id: K) -> str:
        """Display number, e.g. `2.2.1`."""
        return self._numbers[node_id]

    def depth(self, node_id: K) -> int:
        """1 for top-level sections."""
        return self._numbers[node_id].count(".") + 1

    def children(self, node_id: K | None) -> list[K]:
        """Direct children in display order; `None` gives the top-level sections."""
        return list(self._children.get(node_id, []))

    def preorder(self) -> list[K]:
        """All nodes in outline order: 1, 1.1, 1.2, 2, 2.1, ..."""
        return list(self._preorder)

    def ancestors(self, node_id: K) -> list[K]:
        """From the top-level section down to the parent of `node_id`."""
        path: list[K] = []
        parent = self._nodes[node_id].parent_id
        while parent is not None:
            path.append(parent)
            parent = self._nodes[parent].parent_id
        return path[::-1]

    def subtree(self, node_id: K) -> set[K]:
        """`node_id` and all its descendants."""
        found = {node_id}
        stack = [node_id]
        while stack:
            for child in self._children.get(stack.pop(), []):
                found.add(child)
                stack.append(child)
        return found

    def would_create_cycle(self, node_id: K, new_parent_id: K | None) -> bool:
        """True if making `new_parent_id` the parent of `node_id` would create a loop."""
        return new_parent_id is not None and new_parent_id in self.subtree(node_id)


def subtree_counts[K: Hashable](outline: Outline[K], direct: dict[K, int]) -> dict[K, int]:
    """Per node: its own count plus all descendants' (DESIGN rule 7). `direct` may omit nodes."""
    totals: dict[K, int] = {}
    for node_id in reversed(outline.preorder()):  # children before parents
        totals[node_id] = direct.get(node_id, 0) + sum(
            totals[child] for child in outline.children(node_id)
        )
    return totals
