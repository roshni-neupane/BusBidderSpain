# Helpers that build small test objects, so each test only sets what it needs.

from datetime import date, datetime, time, timedelta
from pathlib import Path

from busbidder.models import (Company, Destination, FareConditions, Offer, TravelRequest,
                              TravellerProfile)
from busbidder.scoring import CRITERIA

PROJECT = Path(__file__).resolve().parent.parent
DATA = PROJECT / "data"

COMPANY = Company("SOL", "SolRuta", "Low-cost daytime services")
MALAGA = Destination("MAL", "Malaga", 530, True, True)
SEVILLE = Destination("SEV", "Seville", 530, False, True)
EQUAL_WEIGHTS = {"price": 25, "duration": 25, "departure": 25, "flexibility": 25}


def make_offer(offer_id="SOL-MAL-0712-01", price=30.0, departure="2026-07-12 09:00",
               minutes=480, transfers=0, changeable=False, refundable=False, seats=10,
               destination=MALAGA):
    start = datetime.strptime(departure, "%Y-%m-%d %H:%M")
    return Offer(offer_id, COMPANY, destination, start, start + timedelta(minutes=minutes),
                 price, transfers, FareConditions(changeable, refundable, 20), seats, 4.0, 15.0)


def make_request(budget=50, max_transfers=1, changeable_required=False, preferred=time(9, 0),
                 earliest=date(2026, 7, 12), latest=date(2026, 7, 14)):
    return TravelRequest(MALAGA, earliest, latest, budget, preferred, max_transfers,
                         changeable_required)


def make_profile(weights=None, **request_options):
    return TravellerProfile("test", "Test traveller", "", make_request(**request_options),
                            weights or EQUAL_WEIGHTS, list(CRITERIA))
