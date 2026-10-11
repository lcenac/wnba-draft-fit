import unittest

from draftfit import (
    FitConfig, NEEDS, PoolFilters, Player, SKILLS, breakdown, filter_pool,
    rank_with_breakdown, with_need,
)
from tests.test_fit import guard_heavy_team, mk


def wing_pool():
    return [
        mk("Lockdown", "W", 62, sk=dict(perimeter_defense=85, athleticism=75),
           stats=dict(stl_pct=3.5, blk_pct=1.5, dreb_pct=14.0, pf_per40=2.5, def_rtg=88.0)),
        mk("Solid", "W", 60, sk=dict(perimeter_defense=68),
           stats=dict(stl_pct=2.4, blk_pct=1.0, dreb_pct=12.0, pf_per40=3.2, def_rtg=95.0)),
        mk("Sieve", "W", 70, sk=dict(perimeter_defense=40, spacing=90),
           stats=dict(stl_pct=1.0, blk_pct=0.5, dreb_pct=9.0, pf_per40=4.5, def_rtg=104.0)),
        mk("SwingGuard", "G", 61, secondary_position="W", sk=dict(perimeter_defense=72),
           stats=dict(stl_pct=2.8, blk_pct=0.6, dreb_pct=10.0, pf_per40=2.9, def_rtg=92.0)),
        mk("DefBig", "B", 60, sk=dict(perimeter_defense=70, rim_protection=90)),
    ]


class NeedTests(unittest.TestCase):
    def test_position_filter_primary_vs_secondary(self):
        pool = wing_pool()
        primary = filter_pool(pool, PoolFilters(positions=("W",)))
        both = filter_pool(pool, PoolFilters(positions=("W",), match_secondary=True))
        self.assertNotIn("SwingGuard", [p.name for p in primary])
        self.assertIn("SwingGuard", [p.name for p in both])

    def test_min_skills_filter(self):
        out = filter_pool(wing_pool(), PoolFilters(positions=("W",), min_skills={"perimeter_defense": 60}))
        self.assertEqual({p.name for p in out}, {"Lockdown", "Solid"})

    def test_defensive_wing_need(self):
        cfg = with_need(FitConfig(), "defensive_wing")
        rows = rank_with_breakdown(guard_heavy_team(), wing_pool(), cfg)
        names = [r.player for r, _ in rows]
        # Sieve fails the defense bar, DefBig is not a wing; SwingGuard (G/W, 72) qualifies
        self.assertEqual(set(names), {"Lockdown", "Solid", "SwingGuard"})
        self.assertEqual(names[0], "Lockdown")
        self.assertEqual(rows[0][1]["group"], "defense")

    def test_with_need_does_not_mutate_original(self):
        base = FitConfig()
        with_need(base, "rim_protector")
        self.assertIsNone(base.filters.positions)
        self.assertEqual(base.philosophy.skill_emphasis["rim_protection"], 1.0)
        self.assertIsNone(base.focus_group)

    def test_need_emphasis_multiplies_existing(self):
        base = FitConfig()
        base.philosophy.skill_emphasis["perimeter_defense"] = 2.0
        cfg = with_need(base, "defensive_wing")
        self.assertEqual(cfg.philosophy.skill_emphasis["perimeter_defense"], 6.0)

    def test_breakdown_percentiles_respect_lower_is_better(self):
        pool = wing_pool()[:3]
        bd = breakdown(pool[0], "defense", pool)  # Lockdown: best everywhere
        self.assertAlmostEqual(bd["percentiles"]["stl_pct"], 5 / 6 * 100)
        self.assertAlmostEqual(bd["percentiles"]["def_rtg"], 5 / 6 * 100)  # lowest rtg = best
        worst = breakdown(pool[2], "defense", pool)  # Sieve: worst everywhere
        self.assertLess(worst["percentiles"]["def_rtg"], 20)
        self.assertLess(worst["percentiles"]["pf_per40"], 20)

    def test_breakdown_missing_stats_and_bad_group(self):
        bd = breakdown(mk("NoStats", "W"), "defense")
        self.assertEqual(bd["stats"], {})
        self.assertNotIn("percentiles", bd)
        with self.assertRaises(ValueError):
            breakdown(mk("X", "W"), "nonsense")

    def test_override_stats_what_if(self):
        p = wing_pool()[1]
        better = p.with_overrides(stats={"stl_pct": 4.0})
        self.assertEqual(better.stats["stl_pct"], 4.0)
        self.assertEqual(better.stats["blk_pct"], p.stats["blk_pct"])
        self.assertEqual(p.stats["stl_pct"], 2.4)

    def test_need_config_round_trip_and_validation(self):
        cfg = with_need(FitConfig(), "defensive_wing")
        again = FitConfig.from_json(cfg.to_json())
        self.assertEqual(again.to_dict(), cfg.to_dict())
        self.assertEqual(again.filters.min_skills, {"perimeter_defense": 60})
        with self.assertRaises(ValueError):
            FitConfig(focus_group="nope").validate()
        with self.assertRaises(ValueError):
            FitConfig(filters=PoolFilters(min_skills={"vibes": 90})).validate()

    def test_all_needs_are_valid(self):
        for key in NEEDS:
            with_need(FitConfig(), key)


if __name__ == "__main__":
    unittest.main()
