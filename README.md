# wnba-draft-fit

A draft tool for WNBA teams: how well does a college player fit a team, and who is the best fit for the team's need?

Two modes share one scoring engine:

- **Player explorer** (`rank_teams_for_player`): pick any college player and see how she fits every team, ignoring whether she would be available.
- **Draft room** (`rank_players_for_team`, `rank_with_breakdown`): pick a team and rank the pool by fit. (Next: filter to who is likely still on the board at the team's pick.)

## Quickstart

```python
from draftfit import FitConfig, Player, Team, rank_with_breakdown, with_need

def player(name, pos, **kw):
    return Player(name=name, position=pos, age=22, overall=60, floor=50, ceiling=70, **kw)

team = Team("Example", roster=(
    player("Vet", "G", skills={"spacing": 80}, minutes_share=0.3),
    player("Big", "B", skills={"rim_protection": 70}, minutes_share=0.3),
))
prospects = [
    player("Lockdown", "W", skills={"perimeter_defense": 85},
           stats={"stl_pct": 3.5, "def_rtg": 88.0}),
    player("Solid", "W", skills={"perimeter_defense": 68},
           stats={"stl_pct": 2.4, "def_rtg": 95.0}),
]

config = with_need(FitConfig(), "defensive_wing")
for fit, bd in rank_with_breakdown(team, prospects, config):
    print(fit.explain())
    print("  ", bd["stats"], bd["percentiles"])
```

## Customizing

Everything tunable lives in one JSON-friendly `FitConfig` (`config.to_json()` / `FitConfig.from_json()`):

- **Weights** for the five fit components: skill gap, position need, opportunity, age window, talent.
- **Philosophy**: win-now vs. development, floor vs. ceiling, per-skill emphasis.
- **Pool filters**: position (optionally counting secondary positions), minimum skill ratings, age, school, class year, international players.
- **Need profiles** (`with_need`): `defensive_wing`, `rim_protector`, `floor_spacer`, `table_setter`. Each sets the position filter, skill minimums, emphasis, and which stat breakdown to show.
- **Per-team overrides** and **roster edits** (hypothetical trades or injuries), plus **player what-ifs** (`Player.with_overrides`).

Every fit score comes with a per-component breakdown (`FitResult.contributions`), so you can see why a slider moved a result.

## Your data

`Player.skills` (0-100 ratings for the keys in `draftfit.SKILLS`) and `Player.stats` (raw numbers, named as in `draftfit.STAT_GROUPS`) are the integration points. Map your data into those; the engine does not care where it comes from. The component formulas are simple heuristics, so treat the default weights as a starting point to tune.

## Development

```
python -m unittest discover -s tests -t .
```
