import unittest

from draftfit import (
    FitConfig, FitWeights, Philosophy, PoolFilters, Player, RosterEdit, Team,
    SKILLS, filter_pool, preset, rank_players_for_team, rank_teams_for_player,
    score_fit,
)


def skills(**kw):
    base = {s: 50.0 for s in SKILLS}
    base.update(kw)
    return base


def mk(name, pos, overall=60, age=23, share=0.0, floor=None, ceiling=None, **kw):
    sk = kw.pop("sk", {})
    return Player(
        name=name, position=pos, age=age, skills=skills(**sk), overall=overall,
        floor=overall - 10 if floor is None else floor,
        ceiling=overall + 10 if ceiling is None else ceiling,
        minutes_share=share, **kw,
    )


def guard_heavy_team():
    roster = (
        mk("G1", "G", 70, share=0.15, sk=dict(spacing=80, playmaking=80)),
        mk("G2", "G", 65, share=0.15, sk=dict(spacing=75, playmaking=75)),
        mk("G3", "G", 62, share=0.10, sk=dict(spacing=70)),
        mk("W1", "W", 60, share=0.15, sk=dict(spacing=70)),
        mk("F1", "F", 60, share=0.15, sk=dict(spacing=70)),
        mk("B1", "B", 50, share=0.10, sk=dict(rim_protection=40, rebounding=40)),
    )
    return Team("Guards", roster, open_roster_spots=0)


def big_heavy_team():
    roster = (
        mk("G1", "G", 60, share=0.10, sk=dict(rim_protection=75, rebounding=75)),
        mk("B1", "B", 70, share=0.25, sk=dict(rim_protection=85, rebounding=85)),
        mk("B2", "B", 66, share=0.20, sk=dict(rim_protection=80, rebounding=80)),
        mk("F1", "F", 60, share=0.20, sk=dict(rim_protection=70, rebounding=70)),
        mk("W1", "W", 55, share=0.10, sk=dict(rim_protection=60)),
    )
    return Team("Bigs", roster, open_roster_spots=1)


class FitTests(unittest.TestCase):
    def test_need_drives_team_ranking(self):
        big = mk("Anchor", "B", 68, sk=dict(rim_protection=85, rebounding=85))
        ranked = rank_teams_for_player(big, [guard_heavy_team(), big_heavy_team()])
        self.assertEqual(ranked[0].team, "Guards")
        self.assertGreater(ranked[0].score, ranked[1].score)

    def test_scores_bounded_and_contributions_sum(self):
        p = mk("P", "W", 60)
        r = score_fit(p, guard_heavy_team())
        self.assertTrue(0 <= r.score <= 100)
        self.assertAlmostEqual(sum(r.contributions.values()), r.score)
        for v in r.components.values():
            self.assertTrue(0 <= v <= 1)

    def test_weights_change_ranking(self):
        shooter = mk("Shooter", "G", 55, age=21, sk=dict(spacing=95))
        low = mk("Stud", "G", 90, age=24)
        team = guard_heavy_team()
        talent_cfg = FitConfig(weights=FitWeights(0, 0, 0, 0, 1))
        r = rank_players_for_team(team, [shooter, low], talent_cfg)
        self.assertEqual(r[0].player, "Stud")

    def test_team_override_applies_only_to_that_team(self):
        cfg = FitConfig(team_overrides={"Bigs": {"weights": {"talent": 5.0}}})
        w_bigs, _ = cfg.resolve("Bigs")
        w_other, _ = cfg.resolve("Guards")
        self.assertEqual(w_bigs.talent, 5.0)
        self.assertEqual(w_other.talent, FitWeights().talent)

    def test_development_bias_prefers_young(self):
        young = mk("Young", "W", 55, age=20)
        old = mk("Old", "W", 70, age=25)
        team = guard_heavy_team()
        dev = FitConfig(philosophy=Philosophy(development_bias=1.0),
                        weights=FitWeights(0, 0, 0, 1, 0))
        now = FitConfig(philosophy=Philosophy(development_bias=0.0),
                        weights=FitWeights(0, 0, 0, 1, 0))
        self.assertGreater(score_fit(young, team, dev).score, score_fit(old, team, dev).score)
        self.assertGreater(score_fit(old, team, now).score, score_fit(young, team, now).score)

    def test_risk_tolerance_trusts_ceiling(self):
        boom = mk("Boom", "W", 60, floor=30, ceiling=95)
        cfg_hi = FitConfig(weights=FitWeights(0, 0, 0, 0, 1), philosophy=Philosophy(risk_tolerance=1.0))
        cfg_lo = FitConfig(weights=FitWeights(0, 0, 0, 0, 1), philosophy=Philosophy(risk_tolerance=0.0))
        t = guard_heavy_team()
        self.assertGreater(score_fit(boom, t, cfg_hi).score, score_fit(boom, t, cfg_lo).score)

    def test_skill_emphasis_shifts_fit(self):
        shooter = mk("Shooter", "W", 60, sk=dict(spacing=95))
        rebounder = mk("Reb", "W", 60, sk=dict(rebounding=95))
        team = guard_heavy_team()  # weak rebounding
        cfg = FitConfig(weights=FitWeights(1, 0, 0, 0, 0))
        self.assertGreater(score_fit(rebounder, team, cfg).score,
                           score_fit(shooter, team, cfg).score)

    def test_roster_edit_changes_opportunity(self):
        p = mk("Rookie", "G", 66)
        team = guard_heavy_team()
        before = score_fit(p, team).components["opportunity"]
        edit = RosterEdit(remove=frozenset({"G1", "G2"}))
        after = score_fit(p, team, roster_edit=edit).components["opportunity"]
        self.assertGreater(after, before)
        # original team untouched
        self.assertEqual(len(team.roster), 6)

    def test_player_what_if(self):
        p = mk("Wing", "W", 60, sk=dict(spacing=30))
        team = big_heavy_team()
        base = score_fit(p, team).score
        better = score_fit(p, team, player_overrides={"skills": {"spacing": 90}}).score
        self.assertGreater(better, base)
        self.assertEqual(p.skills["spacing"], 30)  # immutable

    def test_filters(self):
        pool = [
            mk("A", "G", 60, age=21, school="UConn", class_year="JR"),
            mk("B", "B", 50, age=24, school="Iowa", class_year="SR", international=True),
            mk("C", "W", 40, age=22, school="UConn", class_year="SR"),
        ]
        f = PoolFilters(include_international=False, schools=("UConn",), min_overall=50)
        self.assertEqual([p.name for p in filter_pool(pool, f)], ["A"])

    def test_json_round_trip_and_presets(self):
        cfg = preset("development")
        cfg.filters = PoolFilters(positions=("G", "W"), min_age=20)
        cfg.team_overrides = {"Liberty": {"philosophy": {"development_bias": 0.2,
                                                         "skill_emphasis": {"spacing": 2.0}}}}
        again = FitConfig.from_json(cfg.to_json())
        self.assertEqual(again.to_dict(), cfg.to_dict())
        _, phil = again.resolve("Liberty")
        self.assertEqual(phil.skill_emphasis["spacing"], 2.0)
        self.assertEqual(phil.skill_emphasis["rebounding"], 1.0)

    def test_validation(self):
        with self.assertRaises(ValueError):
            FitConfig(weights=FitWeights(-1, 0, 0, 0, 0)).validate()
        with self.assertRaises(ValueError):
            FitConfig(philosophy=Philosophy(risk_tolerance=1.5)).validate()
        with self.assertRaises(ValueError):
            FitConfig(team_overrides={"X": {"weights": {"skill_gap": -2}}}).validate()
        with self.assertRaises(ValueError):
            mk("Bad", "Z")


if __name__ == "__main__":
    unittest.main()
