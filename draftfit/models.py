"""Core data models shared by the fit engine.

A single Player type is used for both college prospects and current roster
players so the same scoring code can compare them directly.
"""
from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Optional

# Skill ratings are 0-100 (50 is roughly league average). Swap in whatever
# your feature pipeline produces; only the keys must match.
SKILLS = (
    "spacing",
    "scoring",
    "playmaking",
    "rebounding",
    "rim_protection",
    "perimeter_defense",
    "athleticism",
)

# G = guard, W = wing, F = forward, B = big
POSITIONS = ("G", "W", "F", "B")


@dataclass(frozen=True)
class Player:
    name: str
    position: str
    age: float
    skills: dict
    overall: float  # projected current-level value, 0-100
    floor: float  # pessimistic outcome, 0-100
    ceiling: float  # optimistic outcome, 0-100
    school: str = ""
    class_year: Optional[str] = None
    secondary_position: Optional[str] = None
    international: bool = False
    minutes_share: float = 0.0  # roster players only: share of team minutes (0-1)
    stats: dict = field(default_factory=dict)  # raw stats, see breakdown.STAT_GROUPS

    def __post_init__(self):
        if self.position not in POSITIONS:
            raise ValueError(f"{self.name}: unknown position {self.position!r}")
        if self.secondary_position and self.secondary_position not in POSITIONS:
            raise ValueError(f"{self.name}: unknown secondary position")
        unknown = set(self.skills) - set(SKILLS)
        if unknown:
            raise ValueError(f"{self.name}: unknown skills {sorted(unknown)}")

    def with_overrides(
        self, skills: Optional[dict] = None, stats: Optional[dict] = None, **fields
    ) -> "Player":
        """Return a copy with edited fields (what-if analysis).

        `skills` and `stats` are merged into the existing dicts rather than
        replacing them.
        """
        merged = dict(self.skills)
        if skills:
            merged.update(skills)
        merged_stats = dict(self.stats)
        if stats:
            merged_stats.update(stats)
        return replace(self, skills=merged, stats=merged_stats, **fields)


@dataclass(frozen=True)
class Team:
    name: str
    roster: tuple = field(default_factory=tuple)  # tuple[Player, ...]
    open_roster_spots: int = 0


@dataclass(frozen=True)
class RosterEdit:
    """A hypothetical change to a team's roster (trade, injury, free agency)."""

    remove: frozenset = frozenset()  # player names
    add: tuple = ()  # tuple[Player, ...]
    open_spots_delta: int = 0

    def apply(self, team: Team) -> Team:
        kept = tuple(p for p in team.roster if p.name not in self.remove)
        freed = len(team.roster) - len(kept)
        return Team(
            name=team.name,
            roster=kept + tuple(self.add),
            open_roster_spots=max(
                0, team.open_roster_spots + freed - len(self.add) + self.open_spots_delta
            ),
        )
