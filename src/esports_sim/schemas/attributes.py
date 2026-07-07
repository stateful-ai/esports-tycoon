"""Attribute registry — the schema that lets the UI, sim, and narrative
layer all agree on what a "player attribute" is without any code change.

Adding a new attribute:
  1. Add an AttributeDefinition to data/attributes.yaml
  2. (Optional) update any heuristic policy that wants to read it

The UI reflects whatever is in the registry; the match engine reads by id
with a sensible default if an attribute is absent.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from esports_sim._compat import StrEnum


class AttributeCategory(StrEnum):
    MECHANICAL = "mechanical"
    TACTICAL = "tactical"
    MENTAL = "mental"
    TEAM = "team"
    PHYSICAL = "physical"


class AttributeVisibility(StrEnum):
    """MVP ships everything FULL. Scouting noise uses HIDDEN/SCOUTED later."""

    FULL = "full"  # always visible to the manager
    SCOUTED = "scouted"  # visible with noise, noise shrinks with scouting
    HIDDEN = "hidden"  # only visible once revealed by in-game events


class AttributeDefinition(BaseModel):
    """A single attribute definition. Declarative; no logic here."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    id: str = Field(..., description="Stable id, used as a dict key everywhere.")
    display_name: str
    category: AttributeCategory
    min_value: float = 1.0
    max_value: float = 99.0
    default: float = 50.0
    visibility: AttributeVisibility = AttributeVisibility.FULL
    # Unused in MVP but reserved so adding fog-of-war later is purely additive.
    scouting_uncertainty: float = 0.0
    description: str = ""


class AttributeRegistry(BaseModel):
    """In-memory registry of all AttributeDefinitions, keyed by id."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    definitions: dict[str, AttributeDefinition]

    def get(self, attr_id: str) -> AttributeDefinition:
        if attr_id not in self.definitions:
            raise KeyError(f"Unknown attribute id: {attr_id}")
        return self.definitions[attr_id]

    def ids(self) -> list[str]:
        return list(self.definitions.keys())

    def by_category(self, category: AttributeCategory) -> list[AttributeDefinition]:
        return [d for d in self.definitions.values() if d.category == category]

    @classmethod
    def from_list(cls, defs: list[AttributeDefinition]) -> "AttributeRegistry":
        return cls(definitions={d.id: d for d in defs})
