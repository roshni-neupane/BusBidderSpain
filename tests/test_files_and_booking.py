# Tests for loader.py, booking.py, experiments.py and the command-line interface.

import contextlib
import io
import json
import random
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from busbidder import cli
from busbidder.booking import BOOKING_REFERENCE_PATTERN, BookingManager
from busbidder.exceptions import BookingError, BusBidderError, DataFileError
from busbidder.loader import Marketplace, load_profiles, read_csv
from busbidder.scoring import CRITERIA
from tests.helpers import DATA, make_offer


class TestLoading(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.market = Marketplace.load(DATA)

    def test_official_data(self):
        self.assertEqual(len(self.market.companies), 5)
        self.assertEqual(len(self.market.destinations), 15)
        self.assertEqual(len(self.market.offers), 743)

    def test_invalid_rows_are_set_aside_with_reasons(self):
        rows = {(item["file"], item["row"]) for item in self.market.review_queue}
        self.assertEqual(len(rows), 14)
        fields = {item["row"]: item["field"] for item in self.market.review_queue}
        self.assertEqual(fields[2], "price_eur")
        self.assertEqual(fields[13], "offer_id")          # duplicate
        self.assertEqual(fields[15], "row")               # too few values

    def test_code_correction(self):
        self.assertEqual(len(self.market.corrections), 2)
        self.assertIn("VRD-MAL-0712-09", self.market.offers)

    def test_sold_out_offers_are_kept(self):
        self.assertTrue(any(o.seats_available == 0 for o in self.market.offers.values()))

    def test_missing_and_broken_files(self):
        with self.assertRaises(DataFileError):
            read_csv(DATA / "no_such_file.csv", ["offer_id"])
        with tempfile.TemporaryDirectory() as folder:
            empty = Path(folder) / "empty.csv"
            empty.write_text("", encoding="utf-8")
            with self.assertRaises(DataFileError):
                read_csv(empty, ["offer_id"])
            wrong = Path(folder) / "wrong.csv"
            wrong.write_text("id,name\n1,x\n", encoding="utf-8")
            with self.assertRaises(DataFileError):
                read_csv(wrong, ["offer_id"])

    def test_profiles(self):
        profiles = load_profiles(DATA / "profiles.json", self.market, list(CRITERIA))
        self.assertEqual(sorted(profiles), ["budget", "business", "flexible"])
        self.assertTrue(profiles["business"].request.changeable_required)

    def test_bad_profiles_file(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "profiles.json"
            data = json.loads((DATA / "profiles.json").read_text(encoding="utf-8"))
            data["budget"]["weights"]["price"] = 10                   # weights no longer total 100
            path.write_text(json.dumps(data), encoding="utf-8")
            with self.assertRaises(DataFileError):
                load_profiles(path, self.market, list(CRITERIA))
            data["budget"]["weights"]["price"] = 60
            data["budget"]["request"]["destination"] = "Lisbon"     # not served
            path.write_text(json.dumps(data), encoding="utf-8")
            with self.assertRaises(DataFileError):
                load_profiles(path, self.market, list(CRITERIA))


class TestBooking(unittest.TestCase):

    def setUp(self):
        self.folder = Path(tempfile.mkdtemp())
        self.path = self.folder / "bookings.json"
        self.manager = BookingManager(self.path, rng=random.Random(1))

    def tearDown(self):
        shutil.rmtree(self.folder)

    def test_booking_reduces_seats_and_is_saved(self):
        offer = make_offer(seats=2, changeable=True)
        booking = self.manager.book(offer, "Ana Lopez")
        self.assertEqual(offer.seats_available, 1)
        self.assertIsNotNone(BOOKING_REFERENCE_PATTERN.fullmatch(booking.reference))
        self.assertTrue(booking.fare["changeable"])
        reloaded = BookingManager(self.path)
        self.assertEqual(reloaded.find(booking.reference).passenger_name, "Ana Lopez")

    def test_capacity_is_reapplied_after_restart(self):
        market = Marketplace()
        offer = make_offer(seats=5)
        market.offers[offer.offer_id] = offer
        self.manager.book(offer, "Ana Lopez")
        self.manager.book(offer, "Jon Perez")
        fresh = make_offer(seats=5)                 # the offer as read again from offers.csv
        market.offers[offer.offer_id] = fresh
        BookingManager(self.path).apply_to_market(market)
        self.assertEqual(fresh.seats_available, 3)

    def test_references_are_unique(self):
        offer = make_offer(seats=40)
        references = {self.manager.book(offer, "Ana Lopez").reference for _ in range(30)}
        self.assertEqual(len(references), 30)

    def test_last_seat_then_sold_out(self):
        offer = make_offer(seats=1)
        self.manager.book(offer, "Ana Lopez")
        with self.assertRaises(BookingError):
            self.manager.book(offer, "Jon Perez")

    def test_invalid_input(self):
        with self.assertRaises(BookingError):
            self.manager.book(make_offer(), "")
        with self.assertRaises(BookingError):
            self.manager.find("BB-26-123")
        with self.assertRaises(BookingError):
            self.manager.find("BB-2026-ZZZZZZ")       # valid format, but no such booking

    def test_cancel_uses_stored_fare_conditions(self):
        market = Marketplace()
        fixed = make_offer("SOL-MAL-0712-01", seats=3)
        flexible = make_offer("SOL-MAL-0712-02", seats=3, changeable=True, refundable=True)
        market.offers = {fixed.offer_id: fixed, flexible.offer_id: flexible}
        a = self.manager.book(fixed, "Ana Lopez")
        b = self.manager.book(flexible, "Ana Lopez")
        self.assertEqual(self.manager.cancel(a.reference, market).refund_eur, 0.0)
        self.assertEqual(self.manager.cancel(b.reference, market).refund_eur, 30.0)
        self.assertEqual(flexible.seats_available, 3)
        with self.assertRaises(BookingError):
            self.manager.cancel(b.reference, market)

    def test_damaged_bookings_file(self):
        self.path.write_text("{ not json", encoding="utf-8")
        with self.assertRaises(DataFileError):
            BookingManager(self.path)


class TestProgram(unittest.TestCase):

    def setUp(self):
        self.folder = Path(tempfile.mkdtemp())
        self.options = ["--data", str(DATA), "--profiles", str(DATA / "profiles.json"),
                        "--bookings", str(self.folder / "bookings.json"),
                        "--output", str(self.folder / "output"), "--log", str(self.folder / "test.log")]

    def tearDown(self):
        shutil.rmtree(self.folder)

    def run_main(self, arguments, answers=None):
        printed = io.StringIO()
        with contextlib.redirect_stdout(printed), mock.patch("builtins.input", side_effect=answers or []):
            code = cli.main(self.options + arguments)
        return code, printed.getvalue()

    def test_rank_command_and_log_file(self):
        code, text = self.run_main(["rank", "--profile", "budget"])
        self.assertEqual(code, 0)
        self.assertIn("SOL-MAL-0714-01 ranks first", text)
        self.assertIn("Set aside", (self.folder / "test.log").read_text(encoding="utf-8"))
        self.assertTrue((self.folder / "output" / "review_queue.csv").exists())

    def test_profiles_get_different_winners(self):
        code, text = self.run_main(["compare"])
        self.assertEqual(code, 0)
        for offer_id in ["SOL-MAL-0714-01", "CST-MAL-0713-01", "VRD-MAL-0713-01"]:
            self.assertIn(offer_id, text)

    def test_menu_booking(self):
        answers = ["1", "1", "1", "Ana Lopez", "y", "0"]
        code, text = self.run_main([], answers)
        self.assertIn("BOOKING CONFIRMED", text)
        saved = json.loads((self.folder / "bookings.json").read_text(encoding="utf-8"))
        self.assertEqual(saved[0]["offer_id"], "SOL-MAL-0714-01")

    def test_menu_own_request_repeats_invalid_answers(self):
        answers = ["3", "Lisbon", "Malaga", "2026-07-32", "2026-07-12", "2026-07-14", "45",
                   "morning", "1", "n",
                   "50", "50", "50", "50",                 # total 200: asked again
                   "40", "25", "15", "20", "", "0"]
        code, text = self.run_main([], answers)
        self.assertIn("is not one of the 15 destinations", text)
        self.assertIn("weights must total 100", text)
        self.assertIn("ranks first", text)

    def test_missing_data_folder(self):
        options = list(self.options)
        options[1] = str(self.folder / "missing")
        printed = io.StringIO()
        with contextlib.redirect_stdout(printed):
            code = cli.main(options + ["rank", "--profile", "budget"])
        self.assertEqual(code, 1)
        self.assertIn("Cannot start", printed.getvalue())

    def test_experiments_are_reproducible(self):
        self.run_main(["experiments"])
        first = (self.folder / "output" / "experiments.md").read_text(encoding="utf-8")
        self.run_main(["experiments"])
        second = (self.folder / "output" / "experiments.md").read_text(encoding="utf-8")
        self.assertEqual(first, second)
        self.assertIn("E3 Weight sensitivity", first)


if __name__ == "__main__":
    unittest.main()


class TestWebInterface(unittest.TestCase):
    """The web API functions, and one real request to the local server."""

    @classmethod
    def setUpClass(cls):
        from busbidder import web
        cls.web = web
        cls.market = Marketplace.load(DATA)
        cls.profiles = load_profiles(DATA / "profiles.json", cls.market, list(CRITERIA))
        cls.meta = web.api_meta(cls.market, cls.profiles)

    def setUp(self):
        self.folder = Path(tempfile.mkdtemp())
        self.bookings = BookingManager(self.folder / "bookings.json")

    def tearDown(self):
        shutil.rmtree(self.folder)

    def payload(self, key="business", **changes):
        profile = next(p for p in self.meta["profiles"] if p["key"] == key)
        data = {"key": key, "name": profile["name"], "method": "hybrid",
                "request": dict(profile["request"]), "weights": dict(profile["weights"])}
        data["request"].update(changes)
        return data

    def test_rank_matches_command_line(self):
        result = self.web.api_rank(self.market, self.payload())
        self.assertEqual(result["ranking"][0]["offer"]["offer_id"], "CST-MAL-0713-01")
        self.assertEqual(sum(r["count"] for r in result["removed"]) + len(result["ranking"]), 743)

    def test_invalid_requests_give_clear_errors(self):
        bad = self.payload()
        bad["weights"]["price"] = 90
        with self.assertRaises(BusBidderError) as caught:
            self.web.api_rank(self.market, bad)
        self.assertIn("100", str(caught.exception))
        with self.assertRaises(BusBidderError):
            self.web.api_rank(self.market, self.payload(earliest="13/07/2026"))
        with self.assertRaises(BusBidderError):
            self.web.api_rank(self.market, self.payload(destination="Lisbon"))

    def test_book_and_cancel_through_api(self):
        offer = self.market.offers["VRD-MAL-0713-01"]
        seats = offer.seats_available
        booking = self.web.api_book(self.market, self.bookings, {"offer_id": "VRD-MAL-0713-01", "name": "Ana Lopez"})
        self.assertEqual(offer.seats_available, seats - 1)
        cancelled = self.web.api_cancel(self.market, self.bookings, {"reference": booking["reference"]})
        self.assertEqual(cancelled["refund_eur"], 47.0)
        self.assertEqual(offer.seats_available, seats)
        with self.assertRaises(BookingError):
            self.web.api_book(self.market, self.bookings, {"offer_id": "NOPE", "name": "Ana Lopez"})

    def test_server_answers(self):
        import threading
        import urllib.request
        server = self.web.make_server(self.market, self.profiles, self.bookings, port=0)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            base = "http://127.0.0.1:" + str(server.server_port)
            page = urllib.request.urlopen(base + "/").read().decode("utf-8")
            self.assertIn("BusBidder", page)
            request = urllib.request.Request(base + "/api/rank", data=json.dumps(self.payload("budget")).encode(),
                                             headers={"Content-Type": "application/json"})
            result = json.loads(urllib.request.urlopen(request).read())
            self.assertEqual(result["ranking"][0]["offer"]["offer_id"], "SOL-MAL-0714-01")
        finally:
            server.shutdown()
            server.server_close()
