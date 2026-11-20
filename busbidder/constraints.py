# Hard constraints: conditions an offer MUST meet before it can be ranked.
#
# Each constraint is a small function registered with the @hard_constraint
# decorator. The registry keeps them in order, so the filter and the user
# interface both read the same list, and a new constraint can be added by
# writing one decorated function without changing filter_offers().

import logging

log = logging.getLogger("busbidder")

HARD_CONSTRAINTS = []       # filled by the decorator below, in this order


class HardConstraint:
    def __init__(self, name, description, removed_reason, check):
        self.name = name
        self.description = description          # the rule, e.g. "has at least one free seat"
        self.removed_reason = removed_reason    # short reason shown to the user
        self.check = check          # function(offer, request) -> True if the offer is acceptable


# Decorator that registers a function as a hard constraint.
def hard_constraint(name, description, removed_reason):
    def register(check):
        HARD_CONSTRAINTS.append(HardConstraint(name, description, removed_reason, check))
        return check
    return register


@hard_constraint("destination", "goes to the requested destination", "other destination")
def goes_to_destination(offer, request):
    return offer.destination.destination_id == request.destination.destination_id


@hard_constraint("travel_window", "departs within the travel window", "outside the travel window")
def departs_in_window(offer, request):
    return request.earliest_date <= offer.departure.date() <= request.latest_date


@hard_constraint("seats", "has at least one free seat", "sold out")
def has_free_seat(offer, request):
    return offer.seats_available > 0


@hard_constraint("budget", "costs no more than the maximum budget", "over the maximum budget")
def within_budget(offer, request):
    return offer.price_eur <= request.max_budget_eur


@hard_constraint("transfers", "has no more than the maximum number of transfers", "too many transfers")
def few_enough_transfers(offer, request):
    return offer.transfers <= request.max_transfers


@hard_constraint("changeable", "is changeable, if the traveller requires it", "not changeable (required)")
def changeable_if_required(offer, request):
    return offer.fare.changeable or not request.changeable_required


class FilterResult:
    """The outcome of filtering: acceptable offers and why the others were removed."""

    def __init__(self):
        self.accepted = []
        self.removed = {c.name: [] for c in HARD_CONSTRAINTS}   # constraint name -> offers

    # Offers removed only by the traveller's own constraints (not destination/date)
    def removed_for_journey(self):
        count = 0
        for name, offers in self.removed.items():
            if name not in ("destination", "travel_window"):
                count = count + len(offers)
        return count


# Applies the hard constraints in order. An offer is removed by the FIRST
# constraint it fails, so every removed offer is counted exactly once.
def filter_offers(offers, request):
    result = FilterResult()
    for offer in offers:
        failed = None
        for constraint in HARD_CONSTRAINTS:
            if not constraint.check(offer, request):
                failed = constraint
                break
        if failed is None:
            result.accepted.append(offer)
        else:
            result.removed[failed.name].append(offer)
    log.info("Filtered %d offers for %s: %d accepted", len(offers),
             request.destination.name, len(result.accepted))
    return result
