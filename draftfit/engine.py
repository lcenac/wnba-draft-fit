"""Fit scoring engine.

score_fit(player, team, config) -> FitResult with a full component breakdown.
Two thin entry points sit on top:
  - rank_teams_for_player  (player explorer mode)
  - rank_players_for_team  (draft room mode, before the availability filter)
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable, Optional

from .breakdown import breakdown
from .config import FitConfig, PoolFilters
from .models import Player, RosterEdit, Team, POSITIONS, SKILLS

ROTATION_MIN_SHARE = 0.05


def _clamp(x: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, x))


@dataclass
class FitResult:
    player: str
    team: str
    score: float  # 0-100
    components: dict  # component -> 0..1
    contributions: dict  # component -> points toward score
    notes: list = field(default_factory=list)

    def explain(self, top: int = 3) -> str:
        ranked = sorted(self.contributions.items(), key=lambda kv: -kv[1])[:top]
        parts = ", ".join(f"{k} +{v:.1f}" for k, v in ranked)
        return f"{self.player} -> {self.team}: {self.score:.1f} ({parts})"


# ---- team profile helpers --------------------------------------------------
def team_skill_profile(team: Team) -> dict:
    """Minutes-weighted average skill rating of the team's rotation."""
    players = [p for p in team.roster if p.minutes_share > 0] or list(team.roster)
    if not players:
        return {s: 0.0 for s in SKILLS}
    total = sum(p.minutes_share for p in players) or float(len(players))
    profile = {}
    for s in SKILLS:
        acc = 0.0
        for p in players:
            w = p.minutes_share if total and p.minutes_share > 0 else 1.0
            acc += w * p.skills.get(s, 50.0)
        denom = sum(p.minutes_share if p.minutes_share > 0 else 1.0 for p in players)
        profile[s] = acc / denom
    return profile


def team_position_shares(team: Team) -> dict:
    """Share of minutes by position (secondary position takes 20% if listed)."""
    shares = {p: 0.0 for p in POSITIONS}
    for pl in team.roster:
        if pl.secondary_position:
            shares[pl.position] += 0.8 * pl.minutes_share
            shares[pl.secondary_position] += 0.2 * pl.minutes_share
        else:
            shares[pl.position] += pl.minutes_share
    return shares


# ---- components ------------------------------------------------------------
def _skill_gap(player: Player, team: Team, config: FitConfig, emphasis: dict):
    profile = team_skill_profile(team)
    target = config.skill_target
    num = den = 0.0
    biggest = None
    for s in SKILLS:
        gap = _clamp((target - profile[s]) / target)
        w = emphasis.get(s, 1.0) * gap
        num += w * player.skills.get(s, 50.0) / 100.0
        den += w
        if biggest is None or w > biggest[1]:
            biggest = (s, w)
    if den == 0:  # no gaps: fall back to emphasis-weighted overall skill level
        tot = sum(emphasis.get(s, 1.0) for s in SKILLS) or 1.0
        val = sum(emphasis.get(s, 1.0) * player.skills.get(s, 50.0) / 100.0 for s in SKILLS) / tot
        return _clamp(val), "team has no clear skill gaps"
    return _clamp(num / den), f"largest team gap: {biggest[0]}"


def _position_need(player: Player, team: Team, config: FitConfig):
    shares = team_position_shares(team)
    need = {
        p: _clamp((config.position_targets[p] - shares[p]) / config.position_targets[p])
        for p in POSITIONS
    }
    if player.secondary_position:
        val = 0.8 * need[player.position] + 0.2 * need[player.secondary_position]
    else:
        val = need[player.position]
    return val, f"{player.position} need {need[player.position]:.2f}"


def _opportunity(player: Player, team: Team):
    rotation = [
        p for p in team.roster
        if p.minutes_share >= ROTATION_MIN_SHARE
        and player.position in (p.position, p.secondary_position)
    ]
    if not rotation:
        pos_opp = 1.0
    else:
        blockers = sum(1 for p in rotation if p.overall >= player.overall)
        pos_opp = 1.0 - blockers / len(rotation)
    room = min(team.open_roster_spots, 2) / 2.0
    return 0.7 * pos_opp + 0.3 * room, f"{len(rotation)} rotation players at {player.position}"


def _age_window(player: Player, philosophy):
    youth = _clamp((25.0 - player.age) / 4.0)  # 21 -> 1.0, 25+ -> 0.0
    readiness = _clamp(player.overall / 100.0)
    b = philosophy.development_bias
    return b * youth + (1 - b) * readiness, None


def _talent(player: Player, philosophy):
    r = philosophy.risk_tolerance
    risk_adj = (1 - r) * player.floor + r * player.ceiling
    return _clamp((0.5 * player.overall + 0.5 * risk_adj) / 100.0), None


# ---- public API ------------------------------------------------------------
def score_fit(
    player: Player,
    team: Team,
    config: Optional[FitConfig] = None,
    roster_edit: Optional[RosterEdit] = None,
    player_overrides: Optional[dict] = None,
) -> FitResult:
    config = config or FitConfig()
    if roster_edit is not None:
        team = roster_edit.apply(team)
    if player_overrides:
        player = player.with_overrides(**player_overrides)

    weights, philosophy = config.resolve(team.name)
    emphasis = philosophy.skill_emphasis

    comps, notes = {}, []
    for name, (val, note) in {
        "skill_gap": _skill_gap(player, team, config, emphasis),
        "position_need": _position_need(player, team, config),
        "opportunity": _opportunity(player, team),
        "age_window": _age_window(player, philosophy),
        "talent": _talent(player, philosophy),
    }.items():
        comps[name] = val
        if note:
            notes.append(f"{name}: {note}")

    w = {k: getattr(weights, k) for k in comps}
    total_w = sum(w.values())
    contributions = {k: 100.0 * w[k] / total_w * comps[k] for k in comps}
    return FitResult(
        player=player.name,
        team=team.name,
        score=sum(contributions.values()),
        components=comps,
        contributions=contributions,
        notes=notes,
    )


def filter_pool(pool: Iterable[Player], f: PoolFilters) -> list:
    out = []
    for p in pool:
        if not f.include_international and p.international:
            continue
        if f.min_age is not None and p.age < f.min_age:
            continue
        if f.max_age is not None and p.age > f.max_age:
            continue
        if f.positions:
            matches = p.position in f.positions or (
                f.match_secondary and p.secondary_position in f.positions
            )
            if not matches:
                continue
        if f.min_skills and any(
            p.skills.get(s, 50.0) < v for s, v in f.min_skills.items()
        ):
            continue
        if f.schools and p.school not in f.schools:
            continue
        if f.class_years and p.class_year not in f.class_years:
            continue
        if f.min_overall is not None and p.overall < f.min_overall:
            continue
        out.append(p)
    return out


def rank_teams_for_player(
    player: Player,
    teams: Iterable[Team],
    config: Optional[FitConfig] = None,
    roster_edits: Optional[dict] = None,  # team name -> RosterEdit
    player_overrides: Optional[dict] = None,
) -> list:
    """Player explorer: fit against every team, ignoring availability."""
    config = config or FitConfig()
    roster_edits = roster_edits or {}
    results = [
        score_fit(player, t, config, roster_edits.get(t.name), player_overrides)
        for t in teams
    ]
    return sorted(results, key=lambda r: -r.score)


def rank_players_for_team(
    team: Team,
    pool: Iterable[Player],
    config: Optional[FitConfig] = None,
    roster_edit: Optional[RosterEdit] = None,
) -> list:
    """Best fits for one team from a (filtered) pool. The draft-room mode
    will intersect this with availability probabilities."""
    config = config or FitConfig()
    candidates = filter_pool(pool, config.filters)
    results = [score_fit(p, team, config, roster_edit) for p in candidates]
    return sorted(results, key=lambda r: -r.score)


def rank_with_breakdown(
    team: Team,
    pool: Iterable[Player],
    config: Optional[FitConfig] = None,
    group: Optional[str] = None,
    roster_edit: Optional[RosterEdit] = None,
    top: Optional[int] = None,
) -> list:
    """Ranked fits for one team, each paired with a stat breakdown.

    Returns a list of (FitResult, breakdown_dict) sorted by fit. The group
    defaults to config.focus_group (set by with_need); percentiles are
    measured against the filtered pool, e.g. other wings who clear the
    minimum defense bar. With no group, the breakdown is None.
    """
    config = config or FitConfig()
    group = group or config.focus_group
    candidates = filter_pool(pool, config.filters)
    scored = sorted(
        ((score_fit(p, team, config, roster_edit), p) for p in candidates),
        key=lambda pair: -pair[0].score,
    )
    if top is not None:
        scored = scored[:top]
    return [
        (res, breakdown(p, group, candidates) if group else None)
        for res, p in scored
    ]
