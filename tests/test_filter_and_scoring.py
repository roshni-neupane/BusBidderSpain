# Tests for constraints.py, scoring.py and explain.py.

import unittest
from datetime import date, time

from busbidder.constraints import HARD_CONSTRAINTS, filter_offers
from busbidder.exceptions import InvalidRequestError, InvalidWeightsError
from busbidder.explain import explain_top_offer
from busbidder.models import TravelRequest, check_weights
from busbidder.scoring import (CRITERIA, criterion, departure_fixed_scale, minutes_between,
                               normalise, rank_offers)
from tests.helpers import MALAGA, SEVILLE, make_offer, make_profile, make_request


class TestHardConstraints(unittest.TestCase):

    def removed_by(self, offer, **request_options):
        result = filter_offers([offer], make_request(**request_options))
        for name, offers in result.removed.items():
            if offers:
                return name
        return None

    def test_boundaries_are_accepted(self):
        self.assertIsNone(self.removed_by(make_offer(price=50.0), budget=50))           # equal to budget
        self.assertIsNone(self.removed_by(make_offer(transfers=1), max_transfers=1))
        self.assertIsNone(self.removed_by(make_offer(departure="2026-07-12 00:00")))   # first day
        self.assertIsNone(self.removed_by(make_offer(departure="2026-07-14 23:45")))   # last day
        self.assertIsNone(self.removed_by(make_offer(seats=1)))

    def test_each_constraint_removes(self):
        self.assertEqual(self.removed_by(make_offer(destination=SEVILLE)), "destination")
        self.assertEqual(self.removed_by(make_offer(departure="2026-07-15 08:00")), "travel_window")
        self.assertEqual(self.removed_by(make_offer(seats=0)), "seats")
        self.assertEqual(self.removed_by(make_offer(price=50.01), budget=50), "budget")
        self.assertEqual(self.removed_by(make_offer(transfers=2), max_transfers=1), "transfers")
        self.assertEqual(self.removed_by(make_offer(changeable=False), changeable_required=True),
                         "changeable")

    def test_each_offer_counted_once(self):
        offers = [make_offer(price=99, seats=0, transfers=3), make_offer(), make_offer(price=99)]
        result = filter_offers(offers, make_request())
        removed = sum(len(group) for group in result.removed.values())
        self.assertEqual(removed + len(result.accepted), 3)
        self.assertEqual(len(result.removed["seats"]), 1)       # first failed constraint counts

    def test_registry_order(self):
        self.assertEqual([c.name for c in HARD_CONSTRAINTS],
                         ["destination", "travel_window", "seats", "budget", "transfers", "changeable"])

    def test_impossible_requests(self):
        with self.assertRaises(InvalidRequestError):
            make_request(budget=0)
        with self.assertRaises(InvalidRequestError):
            make_request(max_transfers=-1)
        with self.assertRaises(InvalidRequestError):
            TravelRequest(MALAGA, date(2026, 7, 14), date(2026, 7, 12), 50, time(9), 1, False)


class TestWeights(unittest.TestCase):

    def test_valid_weights_become_fractions(self):
        fractions = check_weights({"price": 40, "duration": 25, "departure": 15, "flexibility": 20},
                                  list(CRITERIA))
        self.assertAlmostEqual(sum(fractions.values()), 1.0)
        self.assertEqual(fractions["price"], 0.40)

    def test_invalid_weights(self):
        cases = [{"price": 40, "duration": 25, "departure": 15, "flexibility": 19},      # 99 %
                 {"price": -10, "duration": 50, "departure": 40, "flexibility": 20},     # negative
                 {"price": 50, "duration": 50, "departure": 0},                          # missing
                 {"price": 25, "duration": 25, "departure": 25, "flexibility": 25, "rating": 0},
                 {"price": True, "duration": 25, "departure": 25, "flexibility": 49}]
        for weights in cases:
            with self.assertRaises(InvalidWeightsError, msg=str(weights)):
                check_weights(weights, list(CRITERIA))

    def test_profile_setter_keeps_old_weights(self):
        profile = make_profile()
        with self.assertRaises(InvalidWeightsError):
            profile.weights = {"price": 100, "duration": 100, "departure": 0, "flexibility": 0}
        self.assertEqual(profile.weights["price"], 0.25)


class TestScoring(unittest.TestCase):

    def test_normalise(self):
        self.assertEqual(normalise([10, 20, 30], lower_is_better=True), [100, 50, 0])
        self.assertEqual(normalise([10, 20, 30], lower_is_better=False), [0, 50, 100])
        self.assertEqual(normalise([25, 25], lower_is_better=True), [100, 100])   # equal values
        self.assertEqual(normalise([25], lower_is_better=True), [100])            # one offer

    def test_departure_scale_and_midnight(self):
        self.assertEqual(departure_fixed_scale(0), 100)
        self.assertEqual(departure_fixed_scale(180), 50)
        self.assertEqual(departure_fixed_scale(360), 0)
        self.assertEqual(departure_fixed_scale(600), 0)
        self.assertEqual(minutes_between(time(23, 30), time(0, 30)), 60)

    def test_scores_and_totals_stay_between_0_and_100(self):
        profile = make_profile()
        offers = [make_offer("SOL-MAL-0712-0" + str(n), price=20 + n * 7, minutes=300 + n * 40,
                             departure="2026-07-12 0" + str(n) + ":00", changeable=n % 2 == 0)
                  for n in range(1, 6)]
        for method in ("hybrid", "minmax"):
            for item in rank_offers(offers, profile.request, profile.weights, method):
                self.assertTrue(0 <= item.total <= 100)
                for score in item.scores.values():
                    self.assertTrue(0 <= score <= 100)

    def test_ties_are_broken_by_price_then_departure(self):
        profile = make_profile()
        a = make_offer("SOL-MAL-0712-02", departure="2026-07-12 10:00")
        b = make_offer("SOL-MAL-0712-01", departure="2026-07-12 08:00")   # same distance from 09:00
        ranked = rank_offers([a, b], profile.request, profile.weights)
        self.assertAlmostEqual(ranked[0].total, ranked[1].total)
        self.assertIs(ranked[0].offer, b)                                  # earlier departure first
        self.assertEqual([r.rank for r in ranked], [1, 2])

    def test_methods_differ_for_departure(self):
        profile = make_profile()
        offers = [make_offer("SOL-MAL-0712-01", departure="2026-07-12 12:00"),
                  make_offer("SOL-MAL-0712-02", departure="2026-07-12 13:00")]
        hybrid = rank_offers(offers, profile.request, profile.weights, "hybrid")
        minmax = rank_offers(offers, profile.request, profile.weights, "minmax")
        self.assertEqual(hybrid[0].scores["departure"], 50)    # 3 hours away on the fixed scale
        self.assertEqual(minmax[0].scores["departure"], 100)   # best of the two on min-max

    def test_new_criterion_can_be_registered(self):
        @criterion("rating_test", "Rating", "stars", lower_is_better=False)
        def rating_value(offer, request):
            return offer.rating
        try:
            self.assertIn("rating_test", CRITERIA)
        finally:
            del CRITERIA["rating_test"]

    def test_explanation_mentions_strengths_and_caveat(self):
        profile = make_profile(weights={"price": 70, "duration": 10, "departure": 10, "flexibility": 10})
        cheap = make_offer("SOL-MAL-0712-01", price=25, minutes=600)
        fast = make_offer("SOL-MAL-0712-02", price=45, minutes=360)
        ranked = rank_offers([cheap, fast], profile.request, profile.weights)
        text = explain_top_offer(ranked, profile.request, profile.weights)
        self.assertIn("SOL-MAL-0712-01 ranks first", text)
        self.assertIn("lowest price", text)
        self.assertIn("Disadvantage", text)
        self.assertIn("not objectively the best", text)


if __name__ == "__main__":
    unittest.main()
