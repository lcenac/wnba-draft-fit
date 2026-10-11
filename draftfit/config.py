"""Customization layer: everything a user can tune lives in FitConfig.

FitConfig is plain data and round-trips through JSON, so a UI can store
named profiles and per-team overrides without touching engine code.
"""
from __future__ import annotations

import copy
import json
from dataclasses import dataclass, field, asdict, fields, replace
from typing import Optional

from .breakdown import STAT_GROUPS
from .models import SKILLS, POSITIONS


def _check_unit(name: str, value: float) -> None:
    if not 0.0 <= value <= 1.0:
        raise ValueError(f"{name} must be in [0, 1], got {value}")


@dataclass
class FitWeights:
    """Relative importance of each fit component (normalized at scoring time)."""

    skill_gap: float = 0.35  # does she cover skills the team is weak in
    position_need: float = 0.20  # does the team lack depth at her position
    opportunity: float = 0.20  # open minutes / roster spot, few blockers
    age_window: float = 0.10  # age / readiness vs. team timeline
    talent: float = 0.15  # raw projected value (risk-adjusted)

    def validate(self) -> None:
        vals = [getattr(self, f.name) for f in fields(self)]
        if any(v < 0 for v in vals):
            raise ValueError("weights must be non-negative")
        if sum(vals) <= 0:
            raise ValueError("at least one weight must be positive")


@dataclass
class Philosophy:
    development_bias: float = 0.5  # 0 = win-now (ready), 1 = development (young)
    risk_tolerance: float = 0.5  # 0 = trust floor, 1 = trust ceiling
    skill_emphasis: dict = field(default_factory=lambda: {s: 1.0 for s in SKILLS})

    def validate(self) -> None:
        _check_unit("development_bias", self.development_bias)
        _check_unit("risk_tolerance", self.risk_tolerance)
        bad = set(self.skill_emphasis) - set(SKILLS)
        if bad:
            raise ValueError(f"unknown skills in skill_emphasis: {sorted(bad)}")
        if any(v < 0 for v in self.skill_emphasis.values()):
            raise ValueError("skill_emphasis values must be non-negative")


@dataclass
class PoolFilters:
    include_international: bool = True
    min_age: Optional[float] = None
    max_age: Optional[float] = None
    positions: Optional[tuple] = None  # e.g. ("G", "W")
    schools: Optional[tuple] = None
    class_years: Optional[tuple] = None
    min_overall: Optional[float] = None
    # Also count players whose secondary position is in `positions`
    # (e.g. a G/W qualifies as a wing).
    match_secondary: bool = False
    # Minimum skill ratings, e.g. {"perimeter_defense": 60}.
    min_skills: Optional[dict] = None

    def validate(self) -> None:
        if self.positions and set(self.positions) - set(POSITIONS):
            raise ValueError("unknown position in filters")
        if self.min_skills and set(self.min_skills) - set(SKILLS):
            raise ValueError("unknown skill in min_skills")


@dataclass
class FitConfig:
    weights: FitWeights = field(default_factory=FitWeights)
    philosophy: Philosophy = field(default_factory=Philosophy)
    filters: PoolFilters = field(default_factory=PoolFilters)
    # What a solid rotation looks like per skill (0-100); gaps are measured against this.
    skill_target: float = 65.0
    # Ideal share of team minutes by position.
    position_targets: dict = field(
        default_factory=lambda: {"G": 0.25, "W": 0.25, "F": 0.25, "B": 0.25}
    )
    # Partial overrides keyed by team name, e.g.
    # {"Liberty": {"weights": {"skill_gap": 0.5}, "philosophy": {"development_bias": 0.2}}}
    team_overrides: dict = field(default_factory=dict)
    # Which stat group to show in breakdowns (a key of breakdown.STAT_GROUPS).
    focus_group: Optional[str] = None

    # ---- resolution -------------------------------------------------------
    def resolve(self, team_name: str):
        """Return (weights, philosophy) for a team with its overrides applied."""
        ov = self.team_overrides.get(team_name, {})
        weights = replace(self.weights, **ov.get("weights", {}))
        phil_ov = dict(ov.get("philosophy", {}))
        emphasis = dict(self.philosophy.skill_emphasis)
        emphasis.update(phil_ov.pop("skill_emphasis", {}))
        philosophy = replace(self.philosophy, skill_emphasis=emphasis, **phil_ov)
        weights.validate()
        philosophy.validate()
        return weights, philosophy

    def validate(self) -> None:
        self.weights.validate()
        self.philosophy.validate()
        self.filters.validate()
        if self.skill_target <= 0:
            raise ValueError("skill_target must be positive")
        if set(self.position_targets) != set(POSITIONS):
            raise ValueError("position_targets must cover exactly G, W, F, B")
        if self.focus_group is not None and self.focus_group not in STAT_GROUPS:
            raise ValueError(f"unknown focus_group {self.focus_group!r}")
        for team in self.team_overrides:
            self.resolve(team)

    # ---- serialization ----------------------------------------------------
    def to_dict(self) -> dict:
        return asdict(self)

    def to_json(self, **kw) -> str:
        return json.dumps(self.to_dict(), **kw)

    @classmethod
    def from_dict(cls, data: dict) -> "FitConfig":
        data = dict(data)
        filters = dict(data.pop("filters", {}))
        for key in ("positions", "schools", "class_years"):
            if filters.get(key) is not None:
                filters[key] = tuple(filters[key])
        cfg = cls(
            weights=FitWeights(**data.pop("weights", {})),
            philosophy=Philosophy(**data.pop("philosophy", {})),
            filters=PoolFilters(**filters),
            **data,
        )
        cfg.validate()
        return cfg

    @classmethod
    def from_json(cls, text: str) -> "FitConfig":
        return cls.from_dict(json.loads(text))


# ---- need profiles ("we need a defensive wing") ----------------------------
@dataclass
class NeedProfile:
    """A one-click description of what a team is shopping for."""

    name: str
    positions: tuple
    match_secondary: bool = True
    min_skills: dict = field(default_factory=dict)
    skill_emphasis: dict = field(default_factory=dict)  # multipliers on current emphasis
    focus_group: Optional[str] = None  # stat group shown in the breakdown


NEEDS = {
    "defensive_wing": NeedProfile(
        "defensive_wing", ("W",), True,
        min_skills={"perimeter_defense": 60},
        skill_emphasis={"perimeter_defense": 3.0, "athleticism": 1.5},
        focus_group="defense",
    ),
    "rim_protector": NeedProfile(
        "rim_protector", ("B", "F"), False,
        min_skills={"rim_protection": 60},
        skill_emphasis={"rim_protection": 3.0, "rebounding": 1.5},
        focus_group="defense",
    ),
    "floor_spacer": NeedProfile(
        "floor_spacer", ("G", "W", "F"), True,
        min_skills={"spacing": 65},
        skill_emphasis={"spacing": 3.0},
        focus_group="shooting",
    ),
    "table_setter": NeedProfile(
        "table_setter", ("G",), True,
        min_skills={"playmaking": 65},
        skill_emphasis={"playmaking": 3.0},
        focus_group="playmaking",
    ),
}


def with_need(config: FitConfig, need) -> FitConfig:
    """Return a copy of `config` narrowed to a need (a NeedProfile or a key of NEEDS).

    The position filter and minimum skills replace any earlier need; skill
    emphasis multiplies whatever the config already had. Tweak the result
    further (e.g. lower a minimum) like any other config.
    """
    if isinstance(need, str):
        need = NEEDS[need]
    cfg = copy.deepcopy(config)
    cfg.filters.positions = tuple(need.positions)
    cfg.filters.match_secondary = need.match_secondary
    cfg.filters.min_skills = dict(need.min_skills) or None
    emphasis = dict(cfg.philosophy.skill_emphasis)
    for skill, mult in need.skill_emphasis.items():
        emphasis[skill] = emphasis.get(skill, 1.0) * mult
    cfg.philosophy.skill_emphasis = emphasis
    cfg.focus_group = need.focus_group
    cfg.validate()
    return cfg


# ---- presets (starting points a UI can offer) -----------------------------
def preset(name: str) -> FitConfig:
    if name == "balanced":
        return FitConfig()
    if name == "win_now":
        return FitConfig(
            weights=FitWeights(skill_gap=0.30, position_need=0.20, opportunity=0.20,
                               age_window=0.15, talent=0.15),
            philosophy=Philosophy(development_bias=0.1, risk_tolerance=0.2),
        )
    if name == "development":
        return FitConfig(
            weights=FitWeights(skill_gap=0.25, position_need=0.10, opportunity=0.15,
                               age_window=0.20, talent=0.30),
            philosophy=Philosophy(development_bias=0.9, risk_tolerance=0.8),
        )
    raise KeyError(f"unknown preset {name!r}")
