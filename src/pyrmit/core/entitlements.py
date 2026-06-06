"""Immutable entitlement set type for principals.

Entitlements[E] wraps a frozenset[E] with a small predicate API and acts
as the typed input to policy bodies that branch on tier/feature data.
"""

from __future__ import annotations

from collections.abc import Iterator


class Entitlements[E]:
    """A typed, immutable set of entitlement tokens carried on a Principal.

    The type parameter ``E`` is the application's entitlement type
    (typically a ``StrEnum``). The wrapper is intentionally minimal --
    its purpose is to give policy bodies a stable, hashable, set-like
    contract without exposing the underlying ``frozenset`` operations
    that policies do not need.
    """

    __slots__ = ("_items",)

    def __init__(self, items: frozenset[E]) -> None:
        """Construct from a frozenset of entitlement tokens.

        Args:
            items: A frozenset of entitlement values. Must be hashable.
        """
        self._items: frozenset[E] = items

    def has(self, item: E) -> bool:
        """Return True if ``item`` is in this entitlement set."""
        return item in self._items

    def has_any(self, *items: E) -> bool:
        """Return True if at least one of ``items`` is in this set."""
        return any(item in self._items for item in items)

    def has_all(self, *items: E) -> bool:
        """Return True if every item in ``items`` is in this set.

        Note:
            Vacuously True when ``items`` is empty.
        """
        return all(item in self._items for item in items)

    def __contains__(self, item: object) -> bool:
        """Return True if ``item`` is in this entitlement set."""
        return item in self._items

    def __iter__(self) -> Iterator[E]:
        """Iterate over the entitlements in arbitrary (frozenset) order."""
        return iter(self._items)

    def __len__(self) -> int:
        """Return the number of entitlements in this set."""
        return len(self._items)

    def __eq__(self, other: object) -> bool:
        """Structural equality: two ``Entitlements`` are equal iff their sets are."""
        if not isinstance(other, Entitlements):
            return NotImplemented
        # Compare the underlying frozensets. `other._items` is
        # ``frozenset[Unknown]`` post-narrowing, but ``frozenset.__eq__``
        # is defined for any two frozensets and computes set equality
        # over the contained values regardless of declared type. We use
        # ``getattr`` to launder the access through ``object`` so mypy
        # treats the result as ``object`` and the comparison still works.
        other_items: object = other._items
        return self._items == other_items

    def __hash__(self) -> int:
        """Hash by the underlying frozenset; allows use as a dict key."""
        return hash(self._items)

    def __repr__(self) -> str:
        """Render for debugging; intentionally NOT json-serializable."""
        items_repr: list[str] = sorted(repr(item) for item in self._items)
        return f"Entitlements({{{', '.join(items_repr)}}})"

    @classmethod
    def empty(cls) -> Entitlements[E]:
        """Return an empty Entitlements set for type ``E``."""
        return cls(frozenset[E]())

    @classmethod
    def of(cls, *items: E) -> Entitlements[E]:
        """Construct from positional entitlement values.

        Convenience over ``Entitlements(frozenset({Tier.PRO, Tier.FREE}))``::

            Entitlements.of(Tier.PRO, Tier.FREE)
        """
        return cls(frozenset(items))
