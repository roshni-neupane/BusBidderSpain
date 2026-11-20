# Simulated bookings, saved in a JSON file.
#
# Design: the source file offers.csv is never changed. The bookings file is
# the record of what has been sold. When the program starts, the seats of
# every active booking are subtracted from the offers, so capacity is
# always consistent with the saved bookings. No payment details are
# collected; the payment status is only simulated.

import json
import logging
import random
import re
import string
from datetime import datetime
from pathlib import Path

from busbidder.exceptions import BookingError, DataFileError

log = logging.getLogger("busbidder")

# Booking references look like BB-2026-7K3QX9
BOOKING_REFERENCE_PATTERN = re.compile(r"BB-\d{4}-[A-Z0-9]{6}")
NAME_PATTERN = re.compile(r"[A-Za-zÀ-ÿ][A-Za-zÀ-ÿ' .-]{1,59}")


class Booking:
    """One simulated booking, including a copy of the fare conditions."""

    def __init__(self, reference, offer_id, passenger_name, seats, price_eur, company,
                 destination, departure, arrival, fare, created_at,
                 payment_status="simulated: paid", status="active", refund_eur=0.0,
                 profile=None):
        self.reference = reference
        self.offer_id = offer_id
        self.passenger_name = passenger_name
        self.seats = seats
        self.price_eur = price_eur
        self.company = company
        self.destination = destination
        self.departure = departure
        self.arrival = arrival
        self.fare = fare                    # dictionary copied from FareConditions
        self.created_at = created_at
        self.payment_status = payment_status
        self.status = status
        self.refund_eur = refund_eur
        self.profile = profile

    def to_dict(self):
        return dict(self.__dict__)

    @classmethod
    def from_dict(cls, data):
        return cls(**data)

    def confirmation(self):
        fare = self.fare
        lines = [
            "BOOKING CONFIRMED",
            "  Reference:   " + self.reference,
            "  Passenger:   " + self.passenger_name + " (" + str(self.seats) + " seat)",
            "  Journey:     Madrid to " + self.destination + " with " + self.company,
            "  Departure:   " + self.departure + "   Arrival: " + self.arrival,
            "  Price:       EUR {:.2f} ({})".format(self.price_eur * self.seats, self.payment_status),
            "  Fare:        " + fare["level"] + ", luggage " + "{:g}".format(fare["luggage_kg"]) + " kg",
            "  Changes:     " + ("allowed" if fare["changeable"] else "not allowed")
            + ";  Refund: " + ("allowed" if fare["refundable"] else "not allowed"),
        ]
        return "\n".join(lines)


class BookingManager:
    """Creates, saves, finds and cancels bookings."""

    def __init__(self, path, rng=None):
        self.path = Path(path)
        self.rng = rng or random.SystemRandom()
        self.bookings = {}                  # reference -> Booking
        self._load()

    def _load(self):
        if not self.path.exists():
            return
        try:
            with open(self.path, encoding="utf-8") as file:
                data = json.load(file)
            for item in data:
                booking = Booking.from_dict(item)
                self.bookings[booking.reference] = booking
        except (json.JSONDecodeError, TypeError, KeyError) as error:
            raise DataFileError(self.path, "the bookings file is damaged (" + str(error) + ")")

    def save(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(".tmp")
        with open(temporary, "w", encoding="utf-8") as file:
            json.dump([b.to_dict() for b in self.bookings.values()], file, indent=2, ensure_ascii=False)
        temporary.replace(self.path)        # replace in one step, so a crash cannot leave half a file

    # Subtracts the seats of active bookings from the loaded offers.
    def apply_to_market(self, market):
        for booking in self.bookings.values():
            if booking.status != "active":
                continue
            offer = market.offers.get(booking.offer_id)
            if offer is None:
                log.warning("Booking %s refers to unknown offer %s", booking.reference, booking.offer_id)
                continue
            offer.seats_available = max(0, offer.seats_available - booking.seats)

    def new_reference(self):
        characters = string.ascii_uppercase + string.digits
        while True:
            reference = "BB-2026-" + "".join(self.rng.choice(characters) for _ in range(6))
            if reference not in self.bookings:
                return reference

    # Books seats on an offer and saves the booking.
    def book(self, offer, passenger_name, seats=1, profile=None):
        passenger_name = str(passenger_name).strip()
        if NAME_PATTERN.fullmatch(passenger_name) is None:
            raise BookingError("please enter a passenger name of 2-60 letters")
        if seats < 1:
            raise BookingError("at least one seat must be booked")
        if offer.seats_available < seats:
            raise BookingError("offer " + offer.offer_id + " has only "
                               + str(offer.seats_available) + " seat(s) left")

        reference = self.new_reference()
        booking = Booking(reference, offer.offer_id, passenger_name, seats, offer.price_eur,
                          offer.company.name, offer.destination.name,
                          offer.departure.strftime("%Y-%m-%d %H:%M"),
                          offer.arrival.strftime("%Y-%m-%d %H:%M"), offer.fare.to_dict(),
                          datetime.now().strftime("%Y-%m-%d %H:%M:%S"), profile=profile)
        offer.seats_available = offer.seats_available - seats
        self.bookings[reference] = booking
        self.save()
        log.info("Booked %s: offer %s, %d seat(s), %d left", reference, offer.offer_id,
                 seats, offer.seats_available)
        return booking

    # Finds a booking by its reference (the format is checked first).
    def find(self, reference):
        reference = str(reference).strip().upper()
        if BOOKING_REFERENCE_PATTERN.fullmatch(reference) is None:
            raise BookingError("'" + reference + "' is not a valid booking reference (BB-2026-XXXXXX)")
        if reference not in self.bookings:
            raise BookingError("no booking with reference " + reference)
        return self.bookings[reference]

    # Cancels a booking. The stored fare conditions decide the refund.
    def cancel(self, reference, market):
        booking = self.find(reference)
        if booking.status != "active":
            raise BookingError("booking " + booking.reference + " is already cancelled")
        booking.status = "cancelled"
        booking.refund_eur = booking.price_eur * booking.seats if booking.fare["refundable"] else 0.0
        offer = market.offers.get(booking.offer_id)
        if offer is not None:
            offer.seats_available = offer.seats_available + booking.seats
        self.save()
        log.info("Cancelled %s; refund EUR %.2f", booking.reference, booking.refund_eur)
        return booking
