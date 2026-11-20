# Web interface: a small local web server from the Python standard library.
#
# Start it with:  python main.py web      (then open http://127.0.0.1:8000)
#
# The page (static/index.html) sends JSON requests to the /api/... addresses
# below. The api_... functions do the work with the same classes as the
# command-line interface, so they can be tested without starting a server.
# The server only listens on 127.0.0.1, so it is reachable from this computer only.

import json
import logging
import webbrowser
from datetime import date
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

from busbidder.constraints import HARD_CONSTRAINTS, filter_offers
from busbidder.exceptions import BookingError, BusBidderError
from busbidder.explain import explain_top_offer
from busbidder.models import TravelRequest, TravellerProfile
from busbidder.scoring import CRITERIA, METHODS, rank_offers
from busbidder.validation import parse_preferred_time

log = logging.getLogger("busbidder")
PAGE = Path(__file__).resolve().parent / "static" / "index.html"


# ----- functions behind the API (testable without a server) -------------------

def api_meta(market, profiles):
    return {
        "offers": len(market.offers),
        "destinations": sorted(d.name for d in market.destinations.values()),
        "criteria": [{"name": c.name, "label": c.label} for c in CRITERIA.values()],
        "constraints": [{"name": c.name, "description": c.description} for c in HARD_CONSTRAINTS],
        "methods": list(METHODS),
        "profiles": [{
            "key": p.key, "name": p.name, "description": p.description,
            "request": {
                "destination": p.request.destination.name,
                "earliest": p.request.earliest_date.isoformat(),
                "latest": p.request.latest_date.isoformat(),
                "budget": p.request.max_budget_eur,
                "preferred": p.request.preferred_departure.strftime("%H:%M"),
                "transfers": p.request.max_transfers,
                "changeable": p.request.changeable_required},
            "weights": {n: round(w * 100) for n, w in p.weights.items()}}
            for p in profiles.values()],
        "set_aside": len({(r["file"], r["row"]) for r in market.review_queue}),
    }


# Builds a TravellerProfile from the values sent by the page.
def profile_from_payload(market, payload):
    request = payload.get("request", {})
    try:
        earliest = date.fromisoformat(str(request.get("earliest", "")))
        latest = date.fromisoformat(str(request.get("latest", "")))
    except ValueError:
        raise BusBidderError("dates must be written as YYYY-MM-DD")
    try:
        budget = float(request.get("budget"))
        transfers = int(request.get("transfers"))
    except (TypeError, ValueError):
        raise BusBidderError("the budget must be a number and transfers a whole number")
    travel = TravelRequest(market.find_destination(request.get("destination", "")), earliest, latest,
                           budget, parse_preferred_time(request.get("preferred", "")), transfers,
                           bool(request.get("changeable")))
    weights = payload.get("weights", {})
    return TravellerProfile(payload.get("key") or "custom", payload.get("name") or "Custom request",
                            "", travel, weights, list(CRITERIA))


def offer_to_dict(offer):
    return {"offer_id": offer.offer_id, "company": offer.company.name,
            "company_profile": offer.company.profile,
            "departure": offer.departure.strftime("%a %d %b %H:%M"),
            "arrival": offer.arrival.strftime("%a %d %b %H:%M"),
            "price": offer.price_eur, "duration_min": offer.duration_minutes,
            "transfers": offer.transfers, "fare": offer.fare.level(),
            "luggage_kg": offer.fare.luggage_kg, "seats": offer.seats_available,
            "rating": offer.rating, "co2_kg": offer.co2_kg}


def api_rank(market, payload):
    profile = profile_from_payload(market, payload)
    method = payload.get("method", "hybrid")
    if method not in METHODS:
        raise BusBidderError("unknown scoring method '" + str(method) + "'")
    result = filter_offers(list(market.offers.values()), profile.request)
    ranked = rank_offers(result.accepted, profile.request, profile.weights, method)
    return {
        "profile": profile.name,
        "method": method,
        "checked": len(market.offers),
        "removed": [{"reason": c.removed_reason, "count": len(result.removed[c.name])}
                    for c in HARD_CONSTRAINTS],
        "ranking": [{"rank": item.rank, "offer": offer_to_dict(item.offer),
                     "scores": {n: round(v, 1) for n, v in item.scores.items()},
                     "points": {n: round(v, 1) for n, v in item.contributions.items()},
                     "total": round(item.total, 1)} for item in ranked],
        "explanation": explain_top_offer(ranked, profile.request, profile.weights) if ranked else
        "No offer meets all hard constraints. Try a higher budget, more transfers or a wider travel window.",
    }


def booking_to_dict(booking):
    data = booking.to_dict()
    data["confirmation"] = booking.confirmation()
    return data


def api_book(market, bookings, payload):
    offer = market.offers.get(str(payload.get("offer_id", "")))
    if offer is None:
        raise BookingError("unknown offer")
    booking = bookings.book(offer, payload.get("name", ""), profile=payload.get("key"))
    return booking_to_dict(booking)


def api_bookings(bookings):
    return [booking_to_dict(b) for b in sorted(bookings.bookings.values(),
                                                key=lambda b: b.created_at, reverse=True)]


def api_cancel(market, bookings, payload):
    return booking_to_dict(bookings.cancel(payload.get("reference", ""), market))


# ----- the server ----------------------------------------------------------------

def make_handler(market, profiles, bookings):

    class Handler(BaseHTTPRequestHandler):

        def send_json(self, status, data):
            body = json.dumps(data, ensure_ascii=False).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            if self.path in ("/", "/index.html"):
                body = PAGE.read_bytes()
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
            elif self.path == "/api/meta":
                self.send_json(200, api_meta(market, profiles))
            elif self.path == "/api/bookings":
                self.send_json(200, api_bookings(bookings))
            elif self.path == "/api/review":
                self.send_json(200, {"rows": market.review_queue, "corrections": market.corrections})
            else:
                self.send_json(404, {"error": "not found"})

        def do_POST(self):
            try:
                length = int(self.headers.get("Content-Length", 0))
                payload = json.loads(self.rfile.read(length) or b"{}")
            except (ValueError, json.JSONDecodeError):
                self.send_json(400, {"error": "the request is not valid JSON"})
                return
            try:
                if self.path == "/api/rank":
                    self.send_json(200, api_rank(market, payload))
                elif self.path == "/api/book":
                    self.send_json(200, api_book(market, bookings, payload))
                elif self.path == "/api/cancel":
                    self.send_json(200, api_cancel(market, bookings, payload))
                else:
                    self.send_json(404, {"error": "not found"})
            except BusBidderError as error:
                self.send_json(400, {"error": str(error)})

        def log_message(self, format, *args):        # keep the console quiet; use the log file
            log.info("web: " + format, *args)

    return Handler


def make_server(market, profiles, bookings, port=8000):
    return HTTPServer(("127.0.0.1", port), make_handler(market, profiles, bookings))


def run_web(market, profiles, bookings, port=8000, open_browser=True):
    server = make_server(market, profiles, bookings, port)
    address = "http://127.0.0.1:" + str(server.server_port)
    print("BusBidder Spain is running at " + address)
    print("Press Ctrl+C in this window to stop it.")
    log.info("Web interface started at %s", address)
    if open_browser:
        webbrowser.open(address)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped.")
    finally:
        server.server_close()
