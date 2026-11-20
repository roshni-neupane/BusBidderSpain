# Tests for validation.py: regular expressions, conversion and boundary values.

import unittest
from datetime import time

from busbidder.exceptions import InvalidRecordError
from busbidder.loader import Marketplace
from busbidder.validation import (check_row_length, parse_number, parse_offer_id,
                                  parse_preferred_time, parse_whole_number, parse_yes_no,
                                  validate_offer_row)
from tests.helpers import DATA

GOOD_ROW = {"offer_id": "SOL-MAL-0712-01", "company_id": "SOL", "destination_id": "MAL",
            "departure": "2026-07-12 09:00", "arrival": "2026-07-12 17:00", "price_eur": "30.00",
            "transfers": "1", "luggage_kg": "20", "changeable": "no", "refundable": "no",
            "seats_available": "10", "rating": "4.0", "co2_kg": "15.0"}


class TestRegularExpressions(unittest.TestCase):

    def test_valid_offer_id(self):
        offer_id, match = parse_offer_id("SOL-MAL-0712-01")
        self.assertEqual(match.group("company"), "SOL")
        self.assertEqual(match.group("destination"), "MAL")

    def test_invalid_offer_ids(self):
        for text in ["sol-mal-0712-01", "SOL-MAL-712-1", "SOLMAL071201", "SOL-MAL-0712-01X", ""]:
            with self.assertRaises(InvalidRecordError, msg=text):
                parse_offer_id(text)

    def test_preferred_time(self):
        self.assertEqual(parse_preferred_time("morning"), time(9, 0))
        self.assertEqual(parse_preferred_time("08:30"), time(8, 30))
        for text in ["24:00", "8:5", "noon", ""]:
            with self.assertRaises(InvalidRecordError, msg=text):
                parse_preferred_time(text)


class TestBoundaries(unittest.TestCase):

    def test_rating_scale_limits(self):
        self.assertEqual(parse_number("rating", "1.0", 1, 5), 1.0)
        self.assertEqual(parse_number("rating", "5.0", 1, 5), 5.0)
        for text in ["0.9", "5.1", "nan"]:
            with self.assertRaises(InvalidRecordError, msg=text):
                parse_number("rating", text, 1, 5)

    def test_price_must_be_positive(self):
        self.assertEqual(parse_number("price_eur", "0.01", 0.01), 0.01)
        for text in ["0", "-12.00"]:
            with self.assertRaises(InvalidRecordError, msg=text):
                parse_number("price_eur", text, 0.01)

    def test_whole_numbers_and_yes_no(self):
        self.assertEqual(parse_whole_number("seats_available", "0"), 0)
        with self.assertRaises(InvalidRecordError):
            parse_whole_number("seats_available", "-3")
        with self.assertRaises(InvalidRecordError):
            parse_whole_number("transfers", "one")
        self.assertTrue(parse_yes_no("changeable", "YES"))
        with self.assertRaises(InvalidRecordError):
            parse_yes_no("changeable", "maybe")


class TestRows(unittest.TestCase):

    def setUp(self):
        self.market = Marketplace()
        self.market.load_companies(DATA / "companies.csv")
        self.market.load_destinations(DATA / "destinations.csv")

    def check(self, **changes):
        row = dict(GOOD_ROW)
        row.update(changes)
        return validate_offer_row(row, self.market.companies, self.market.destinations)

    def problem_fields(self, **changes):
        with self.assertRaises(InvalidRecordError) as caught:
            self.check(**changes)
        return [field for field, reason in caught.exception.problems]

    def test_valid_row(self):
        values = self.check()
        self.assertEqual(values["price_eur"], 30.0)
        self.assertIsInstance(values["transfers"], int)

    def test_optional_emissions_may_be_empty(self):
        self.assertIsNone(self.check(co2_kg="")["co2_kg"])

    def test_inconsistent_values(self):
        self.assertEqual(self.problem_fields(arrival="2026-07-12 08:00"), ["arrival"])
        self.assertEqual(self.problem_fields(arrival="2026-07-12 09:00"), ["arrival"])   # equal is not after
        self.assertEqual(self.problem_fields(refundable="yes"), ["refundable"])
        self.assertEqual(self.problem_fields(destination_id="SEV"), ["offer_id"])         # ID says MAL

    def test_unknown_codes_and_impossible_dates(self):
        self.assertIn("destination_id", self.problem_fields(destination_id="XYZ", offer_id="SOL-XYZ-0712-01"))
        self.assertIn("company_id", self.problem_fields(company_id="BUS", offer_id="BUS-MAL-0712-01"))
        self.assertIn("departure", self.problem_fields(departure="2026-07-32 09:00"))

    def test_all_problems_are_reported(self):
        fields = self.problem_fields(price_eur="-5", rating="6.2", seats_available="-1")
        self.assertEqual(fields, ["price_eur", "seats_available", "rating"])

    def test_row_length(self):
        short_row = dict(GOOD_ROW)
        short_row["co2_kg"] = None
        with self.assertRaises(InvalidRecordError):
            check_row_length(short_row, list(GOOD_ROW))
        long_row = dict(GOOD_ROW)
        long_row[None] = ["extra"]
        with self.assertRaises(InvalidRecordError):
            check_row_length(long_row, list(GOOD_ROW))


if __name__ == "__main__":
    unittest.main()
