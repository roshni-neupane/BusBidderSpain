# Domain classes: the things that exist in the BusBidder Spain marketplace.
#
# Composition is used throughout: an Offer HAS a Company, a Destination and
# FareConditions; a TravellerProfile HAS a TravelRequest and weights.

from datetime import time

from busbidder.exceptions import InvalidRequestError, InvalidWeightsError


class Company:
    """One of the five bus companies."""

    def __init__(self, company_id, name, profile):
        self.company_id = company_id
        self.name = name
        self.profile = profile


class Destination:
    """A city served from the Madrid hub."""

    def __init__(self, destination_id, name, distance_km, coastal, major_city):
        self.destination_id = destination_id
        self.name = name
        self.distance_km = distance_km
        self.coastal = coastal
        self.major_city = major_city


class FareConditions:
    """The ticket rules of an offer: changes, refunds and luggage."""

    # Points used by the flexibility criterion (a categorical value)
    FLEXIBILITY_POINTS = {"fixed": 0, "changeable": 60, "changeable and refundable": 100}

    def __init__(self, changeable, refundable, luggage_kg):
        self.changeable = changeable
        self.refundable = refundable
        self.luggage_kg = luggage_kg

    # Returns "fixed", "changeable" or "changeable and refundable".
    def level(self):
        if self.changeable and self.refundable:
            return "changeable and refundable"
        if self.changeable:
            return "changeable"
        return "fixed"

    def flexibility_points(self):
        return self.FLEXIBILITY_POINTS[self.level()]

    def to_dict(self):
        return {"changeable": self.changeable, "refundable": self.refundable,
                "luggage_kg": self.luggage_kg, "level": self.level()}


class Offer:
    """One bus departure offered by one company, with its price and conditions."""

    def __init__(self, offer_id, company, destination, departure, arrival, price_eur,
                 transfers, fare, seats_available, rating, co2_kg):
        self.offer_id = offer_id
        self.company = company                  # Company object
        self.destination = destination          # Destination object
        self.departure = departure              # datetime
        self.arrival = arrival                  # datetime
        self.price_eur = price_eur
        self.transfers = transfers
        self.fare = fare                        # FareConditions object
        self.seats_available = seats_available
        self.rating = rating
        self.co2_kg = co2_kg                    # None when unknown

    @property
    def duration_minutes(self):
        return int((self.arrival - self.departure).total_seconds() // 60)


# Named parts of the day that a traveller can use instead of an exact time
NAMED_TIMES = {"morning": time(9, 0), "afternoon": time(14, 0),
               "evening": time(19, 0), "night": time(23, 0)}


class TravelRequest:
    """What one traveller needs: the hard constraints and the preferred time."""

    def __init__(self, destination, earliest_date, latest_date, max_budget_eur,
                 preferred_departure, max_transfers, changeable_required):
        if latest_date < earliest_date:
            raise InvalidRequestError("the travel window ends before it starts")
        if max_budget_eur <= 0:
            raise InvalidRequestError("the budget must be more than 0 euros")
        if max_transfers < 0:
            raise InvalidRequestError("the maximum number of transfers cannot be negative")

        self.destination = destination          # Destination object
        self.earliest_date = earliest_date      # date
        self.latest_date = latest_date          # date
        self.max_budget_eur = max_budget_eur
        self.preferred_departure = preferred_departure   # time
        self.max_transfers = max_transfers
        self.changeable_required = changeable_required


class TravellerProfile:
    """A named traveller: a request plus how important each criterion is.

    The weights are protected (_weights) and can only be set through a
    property that checks them, so a profile can never hold weights that do
    not total 100 %.
    """

    def __init__(self, key, name, description, request, weights, criterion_names):
        self.key = key
        self.name = name
        self.description = description
        self.request = request                  # TravelRequest object
        self._criterion_names = list(criterion_names)
        self.weights = weights                  # checked by the setter below

    @property
    def weights(self):
        return dict(self._weights)

    @weights.setter
    def weights(self, weights):
        self._weights = check_weights(weights, self._criterion_names)


# Checks a dictionary of weights given in per cent.
# Every criterion needs a weight of 0 or more, and together they must be 100.
# Returns the weights as fractions (e.g. 40 -> 0.40).
def check_weights(weights, criterion_names):
    missing = [name for name in criterion_names if name not in weights]
    unknown = [name for name in weights if name not in criterion_names]
    if missing:
        raise InvalidWeightsError("missing weight for: " + ", ".join(missing))
    if unknown:
        raise InvalidWeightsError("unknown criterion: " + ", ".join(unknown))

    for name, value in weights.items():
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise InvalidWeightsError("weight for " + name + " must be a number")
        if value < 0:
            raise InvalidWeightsError("weight for " + name + " cannot be negative")

    total = sum(weights.values())
    if abs(total - 100) > 0.001:
        raise InvalidWeightsError("weights must total 100 %, but they total "
                                  + "{:g}".format(total) + " %")

    fractions = {}
    for name in criterion_names:
        fractions[name] = weights[name] / 100
    return fractions
