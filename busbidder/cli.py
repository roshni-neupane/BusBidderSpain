# Command-line interface: an interactive menu and a few direct commands.
#
#   python main.py                               interactive menu
#   python main.py web                           web interface in the browser
#   python main.py rank --profile budget         ranking for one profile
#   python main.py compare                       the three profiles side by side
#   python main.py experiments                   evidence files for the report
#   python main.py book --profile budget --rank 1 --name "Ana Lopez"

import argparse
import sys
from datetime import date
from pathlib import Path

from busbidder.booking import BookingManager
from busbidder.constraints import filter_offers
from busbidder.display import LINE, format_filter_summary, format_ranking, format_request
from busbidder.exceptions import BusBidderError, DataFileError
from busbidder.explain import explain_top_offer
from busbidder.loader import Marketplace, load_profiles
from busbidder.logging_setup import configure_logging
from busbidder.models import TravelRequest, TravellerProfile
from busbidder.scoring import CRITERIA, METHODS, rank_offers
from busbidder.validation import parse_preferred_time

# Weights suggested in the project specification, used for "my own request"
DEFAULT_WEIGHTS = {"price": 40, "duration": 25, "departure": 15, "flexibility": 20}


class App:
    """Holds the loaded data and runs one search, comparison or booking."""

    def __init__(self, market, profiles, bookings, method="hybrid", output=print, ask=None):
        self.market = market
        self.profiles = profiles
        self.bookings = bookings
        self.method = method
        self.output = output                # print function (replaceable in tests)
        self.ask = ask or (lambda question: input(question))   # replaceable in tests

    # Filters and ranks the offers for one profile.
    def search(self, profile):
        result = filter_offers(list(self.market.offers.values()), profile.request)
        ranked = rank_offers(result.accepted, profile.request, profile.weights, self.method)
        return result, ranked

    def show_search(self, profile, top=10):
        result, ranked = self.search(profile)
        self.output(LINE)
        self.output(format_request(profile))
        self.output("")
        self.output(format_filter_summary(result, len(self.market.offers)))
        self.output("")
        if not ranked:
            self.output("No offer meets all hard constraints. Try a higher budget, more "
                        "transfers or a wider travel window.")
            return ranked
        self.output(format_ranking(ranked, top))
        self.output("")
        self.output("Why this offer ranks first:")
        self.output(explain_top_offer(ranked, profile.request, profile.weights))
        return ranked

    def compare_profiles(self):
        self.output("The same " + str(len(self.market.offers)) + " offers ranked for each profile ("
                    + self.method + " scoring):")
        for profile in self.profiles.values():
            result, ranked = self.search(profile)
            self.output("")
            self.output(profile.name + " - " + str(len(ranked)) + " acceptable offers")
            self.output(format_ranking(ranked, 3))

    def book(self, ranked, rank, passenger_name, profile_key=None):
        if rank < 1 or rank > len(ranked):
            raise BusBidderError("rank must be between 1 and " + str(len(ranked)))
        booking = self.bookings.book(ranked[rank - 1].offer, passenger_name, profile=profile_key)
        self.output(booking.confirmation())
        return booking

    # ----- interactive menu -------------------------------------------------

    def menu(self):
        while True:
            self.output("")
            self.output("BusBidder Spain - bus offers from Madrid")
            self.output("  1  Rank offers for a traveller profile")
            self.output("  2  Compare the traveller profiles")
            self.output("  3  Enter my own request and weights")
            self.output("  4  View or cancel a booking")
            self.output("  5  Show rows set aside for review")
            self.output("  0  Quit")
            choice = self.ask("Choose: ").strip()
            try:
                if choice == "1":
                    profile = self.choose_profile()
                    if profile is not None:
                        self.search_and_book(profile)
                elif choice == "2":
                    self.compare_profiles()
                elif choice == "3":
                    self.search_and_book(self.ask_own_request())
                elif choice == "4":
                    self.manage_booking()
                elif choice == "5":
                    self.show_review_queue()
                elif choice == "0":
                    self.output("Goodbye.")
                    return
                else:
                    self.output("Please choose a number from the menu.")
            except BusBidderError as error:
                self.output("Problem: " + str(error))

    def choose_profile(self):
        keys = list(self.profiles)
        for number, key in enumerate(keys, start=1):
            self.output("  " + str(number) + "  " + self.profiles[key].name)
        answer = self.ask("Profile number: ").strip()
        if not answer.isdigit() or not 1 <= int(answer) <= len(keys):
            self.output("Unknown profile.")
            return None
        return self.profiles[keys[int(answer) - 1]]

    def search_and_book(self, profile):
        ranked = self.show_search(profile)
        if not ranked:
            return
        answer = self.ask("\nEnter a rank number to book that offer, or press Enter to go back: ").strip()
        if answer == "":
            return
        if not answer.isdigit():
            self.output("Please enter a number.")
            return
        item = ranked[int(answer) - 1] if 1 <= int(answer) <= len(ranked) else None
        if item is None:
            self.output("There is no offer with that rank.")
            return
        offer = item.offer
        self.output("You chose " + offer.offer_id + ": " + offer.company.name + ", "
                    + offer.departure.strftime("%d %b %H:%M") + ", EUR {:.2f}, {} fare, {} seat(s) left."
                    .format(offer.price_eur, offer.fare.level(), offer.seats_available))
        name = self.ask("Passenger name: ")
        if self.ask("Confirm booking? (y/n): ").strip().lower() != "y":
            self.output("Booking not made.")
            return
        self.book(ranked, int(answer), name, profile.key)

    # Asks for a request and weights, repeating each question until it is valid.
    def ask_own_request(self):
        names = ", ".join(sorted(d.name for d in self.market.destinations.values()))
        self.output("Destinations: " + names)
        destination = self.ask_until_valid("Destination: ", self.market.find_destination)
        earliest = self.ask_until_valid("Earliest date (YYYY-MM-DD, offers exist 2026-07-10 to 2026-07-16): ",
                                        date.fromisoformat)
        latest = self.ask_until_valid("Latest date (YYYY-MM-DD): ", date.fromisoformat)
        budget = self.ask_until_valid("Maximum budget in EUR: ", float)
        preferred = self.ask_until_valid("Preferred departure (morning, afternoon, evening, night or HH:MM): ",
                                         parse_preferred_time)
        transfers = self.ask_until_valid("Maximum transfers (0, 1, ...): ", int)
        changeable = self.ask("Changeable ticket required? (y/n): ").strip().lower() == "y"
        request = TravelRequest(destination, earliest, latest, budget, preferred, transfers, changeable)

        self.output("How important is each criterion? The four numbers must total 100.")
        self.output("Press Enter to use the example weights 40 / 25 / 15 / 20.")
        while True:
            weights = {}
            for name in CRITERIA:
                text = self.ask("  " + CRITERIA[name].label + " (%): ").strip()
                if text == "":
                    weights = dict(DEFAULT_WEIGHTS)
                    break
                weights[name] = self.convert(text, float)
            try:
                return TravellerProfile("custom", "Your request", "entered in the menu",
                                        request, weights, list(CRITERIA))
            except BusBidderError as error:
                self.output("Problem: " + str(error) + ". Please enter the weights again.")

    def ask_until_valid(self, question, convert):
        while True:
            text = self.ask(question).strip()
            try:
                return convert(text)
            except (ValueError, BusBidderError) as error:
                self.output("Problem: " + str(error) + ". Please try again.")

    def convert(self, text, convert):
        try:
            return convert(text)
        except ValueError:
            return float("nan")             # rejected by the weight check

    def manage_booking(self):
        booking = self.bookings.find(self.ask("Booking reference (BB-2026-XXXXXX): "))
        self.output(booking.confirmation())
        self.output("  Status:      " + booking.status)
        if booking.status == "active" and self.ask("Cancel this booking? (y/n): ").strip().lower() == "y":
            booking = self.bookings.cancel(booking.reference, self.market)
            self.output("Booking cancelled. Refund: EUR {:.2f}".format(booking.refund_eur))

    def show_review_queue(self):
        rows = {}
        for item in self.market.review_queue:
            rows.setdefault((item["file"], item["row"]), []).append(item["field"] + ": " + item["reason"])
        self.output(str(len(rows)) + " rows were set aside for review (not used):")
        for (source, row), reasons in rows.items():
            self.output("  " + source + " row " + str(row) + " - " + "; ".join(reasons))
        for text in self.market.corrections:
            self.output("  corrected: " + text)


def build_parser():
    parser = argparse.ArgumentParser(prog="main.py", description="BusBidder Spain")
    parser.add_argument("--data", default="data", help="folder with the data files")
    parser.add_argument("--profiles", default="data/profiles.json", help="traveller profiles (JSON)")
    parser.add_argument("--bookings", default="storage/bookings.json", help="bookings file")
    parser.add_argument("--output", default="output", help="folder for output files")
    parser.add_argument("--log", default="logs/busbidder.log", help="log file")
    parser.add_argument("--method", choices=METHODS, default="hybrid", help="score normalisation method")
    commands = parser.add_subparsers(dest="command")
    commands.add_parser("menu", help="interactive menu (default)")
    web = commands.add_parser("web", help="web interface in the browser (http://127.0.0.1:8000)")
    web.add_argument("--port", type=int, default=8000)
    web.add_argument("--no-browser", action="store_true", help="do not open the browser automatically")
    rank = commands.add_parser("rank", help="rank offers for one profile")
    rank.add_argument("--profile", required=True)
    rank.add_argument("--top", type=int, default=10)
    commands.add_parser("compare", help="compare all profiles")
    commands.add_parser("experiments", help="write the experiment results to the output folder")
    book = commands.add_parser("book", help="book an offer from a profile's ranking")
    book.add_argument("--profile", required=True)
    book.add_argument("--rank", type=int, default=1)
    book.add_argument("--name", required=True)
    return parser


def main(arguments=None):
    args = build_parser().parse_args(arguments)
    configure_logging(args.log)
    try:
        market = Marketplace.load(args.data)
        market.write_review_queue(Path(args.output) / "review_queue.csv")
        profiles = load_profiles(args.profiles, market, list(CRITERIA))
        bookings = BookingManager(args.bookings)
        if args.command != "experiments":
            # The experiments always use the original data, so their results
            # do not change when seats are booked (reproducible evidence).
            bookings.apply_to_market(market)
        app = App(market, profiles, bookings, args.method)

        if args.command in (None, "menu"):
            app.menu()
        elif args.command == "web":
            from busbidder.web import run_web
            run_web(market, profiles, bookings, args.port, not args.no_browser)
        elif args.command == "rank":
            if args.profile not in profiles:
                raise BusBidderError("unknown profile '" + args.profile + "'; choose from "
                                     + ", ".join(profiles))
            app.show_search(profiles[args.profile], args.top)
        elif args.command == "compare":
            app.compare_profiles()
        elif args.command == "experiments":
            from busbidder.experiments import run_experiments
            written = run_experiments(market, profiles, args.output)
            print("Experiment results written to:")
            for path in written:
                print("  " + Path(path).as_posix())
        elif args.command == "book":
            if args.profile not in profiles:
                raise BusBidderError("unknown profile '" + args.profile + "'")
            result, ranked = app.search(profiles[args.profile])
            app.book(ranked, args.rank, args.name, args.profile)
    except DataFileError as error:
        print("Cannot start: " + str(error))
        return 1
    except BusBidderError as error:
        print("Problem: " + str(error))
        return 1
    except (KeyboardInterrupt, EOFError):
        print("\nStopped.")
        return 0
    return 0


if __name__ == "__main__":
    sys.exit(main())
