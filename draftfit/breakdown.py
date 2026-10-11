"""Stat breakdowns: show a player's numbers for one area (defense, shooting...)
and where each number ranks within a pool.

Skill keys must exist in models.SKILLS. Stat keys are free-form entries in
Player.stats, so map your raw data columns to these names (or edit STAT_GROUPS).
"""
from __future__ import annotations

from typing import Iterable, Optional

from .models import Player

STAT_GROUPS = {
    "defense": {
        "skills": ("perimeter_defense", "rim_protection", "athleticism"),
        "stats": ("stl_pct", "blk_pct", "dreb_pct", "pf_per40", "def_rtg"),
    },
    "shooting": {
        "skills": ("spacing", "scoring"),
        "stats": ("three_pt_pct", "three_pa_per40", "ft_pct", "efg_pct", "ts_pct"),
    },
    "playmaking": {
        "skills": ("playmaking",),
        "stats": ("ast_pct", "tov_pct", "ast_tov"),
    },
    "rebounding": {
        "skills": ("rebounding", "athleticism"),
        "stats": ("oreb_pct", "dreb_pct", "reb_per40"),
    },
}

# For these stats a smaller number is better, so percentiles are inverted.
LOWER_IS_BETTER = frozenset({"pf_per40", "def_rtg", "tov_pct"})


def _percentile(value: float, values: list, lower_better: bool) -> Optional[float]:
    if not values:
        return None
    if lower_better:
        beaten = sum(1 for v in values if v > value)
    else:
        beaten = sum(1 for v in values if v < value)
    ties = sum(1 for v in values if v == value)
    return 100.0 * (beaten + 0.5 * ties) / len(values)


def breakdown(player: Player, group: str, pool: Optional[Iterable[Player]] = None) -> dict:
    """Skill ratings and raw stats for one group, with pool percentiles if given.

    Percentiles are 0-100 where higher is always better (inverted for
    lower-is-better stats such as def_rtg or fouls).
    """
    if group not in STAT_GROUPS:
        raise ValueError(f"unknown stat group {group!r}; choose from {sorted(STAT_GROUPS)}")
    spec = STAT_GROUPS[group]
    skills = {s: player.skills.get(s, 50.0) for s in spec["skills"]}
    stats = {k: player.stats[k] for k in spec["stats"] if k in player.stats}
    out = {
        "player": player.name,
        "group": group,
        "skills": skills,
        "group_rating": sum(skills.values()) / len(skills),
        "stats": stats,
    }
    if pool is not None:
        pool = list(pool)
        out["percentiles"] = {
            k: _percentile(
                v, [p.stats[k] for p in pool if k in p.stats], k in LOWER_IS_BETTER
            )
            for k, v in stats.items()
        }
    return out
