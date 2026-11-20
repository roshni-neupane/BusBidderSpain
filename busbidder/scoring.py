# Weighted multi-criteria ranking.
#
# 1. Each criterion gives a RAW value for an offer (euros, minutes, points).
# 2. The raw value is converted to a 0-100 SCORE. Two methods exist:
#
#    "hybrid" (the final design, used by default)
#       - price and duration use min-max normalisation among the offers that
#         passed the hard constraints, because euros and minutes have no
#         natural 0-100 scale;
#       - departure and flexibility use a FIXED scale, so their score does
#         not depend on which other offers happen to be available:
#           departure:   100 at the preferred time, falling evenly to 0 at
#                        6 hours (360 minutes) away or more;
#           flexibility: fixed 0 / 60 / 100 points (see FareConditions).
#
#    "minmax" (the first version, kept for comparison in the report)
#       - every criterion uses min-max normalisation.
#
#    Min-max:  lower-is-better:  score = 100 * (max - value) / (max - min)
#              higher-is-better: score = 100 * (value - min) / (max - min)
#    If all offers have the same value, every offer gets 100 for that
#    criterion: it cannot separate them, so it does not change the order.
#
# 3. TOTAL = sum of weight * score, which is again on a 0-100 scale.
#
# Criteria are registered with the @criterion decorator. Adding a new
# criterion means writing one function; the ranking code does not change.

import logging

log = logging.getLogger("busbidder")

CRITERIA = {}               # name -> Criterion, filled by the decorator
METHODS = ("hybrid", "minmax")
DEPARTURE_ZERO_MINUTES = 360        # 6 hours from the preferred time scores 0


class Criterion:
    def __init__(self, name, label, unit, lower_is_better, raw_value, fixed_scale):
        self.name = name
        self.label = label
        self.unit = unit
        self.lower_is_better = lower_is_better
        self.raw_value = raw_value          # function(offer, request) -> number
        self.fixed_scale = fixed_scale      # function(raw) -> 0-100, or None


# Decorator that registers a function as a ranking criterion.
def criterion(name, label, unit, lower_is_better, fixed_scale=None):
    def register(raw_value):
        CRITERIA[name] = Criterion(name, label, unit, lower_is_better, raw_value, fixed_scale)
        return raw_value
    return register


def departure_fixed_scale(minutes_away):
    return max(0.0, 100 * (1 - minutes_away / DEPARTURE_ZERO_MINUTES))


def flexibility_fixed_scale(points):
    return float(points)


@criterion("price", "Price", "EUR", lower_is_better=True)
def price_value(offer, request):
    return offer.price_eur


@criterion("duration", "Duration", "min", lower_is_better=True)
def duration_value(offer, request):
    return offer.duration_minutes


@criterion("departure", "Departure convenience", "min from preferred", lower_is_better=True,
           fixed_scale=departure_fixed_scale)
def departure_value(offer, request):
    return minutes_between(offer.departure.time(), request.preferred_departure)


@criterion("flexibility", "Flexibility", "points", lower_is_better=False,
           fixed_scale=flexibility_fixed_scale)
def flexibility_value(offer, request):
    return offer.fare.flexibility_points()


# Minutes between two clock times, going round midnight if that is shorter
# (23:30 is 60 minutes from 00:30, not 1380).
def minutes_between(first, second):
    a = first.hour * 60 + first.minute
    b = second.hour * 60 + second.minute
    difference = abs(a - b)
    return min(difference, 24 * 60 - difference)


# Min-max normalisation of a list of raw values to 0-100.
def normalise(values, lower_is_better):
    lowest = min(values)
    highest = max(values)
    if highest == lowest:
        return [100.0 for value in values]
    scores = []
    for value in values:
        if lower_is_better:
            scores.append(100 * (highest - value) / (highest - lowest))
        else:
            scores.append(100 * (value - lowest) / (highest - lowest))
    return scores


# Converts the raw values of one criterion to scores with the chosen method.
def score_criterion(crit, values, method):
    if method not in METHODS:
        raise ValueError("unknown normalisation method '" + str(method) + "'")
    if method == "hybrid" and crit.fixed_scale is not None:
        return [crit.fixed_scale(value) for value in values]
    return normalise(values, crit.lower_is_better)


class RankedOffer:
    """One offer in the ranking, with its raw values, scores and total."""

    def __init__(self, offer, raw, scores, contributions, total):
        self.offer = offer
        self.raw = raw                      # criterion name -> raw value
        self.scores = scores                # criterion name -> 0-100 score
        self.contributions = contributions  # criterion name -> weight * score
        self.total = total
        self.rank = None


# Ranks offers for one request with weights given as fractions (total 1.0).
# Ties are broken by lower price, then earlier departure, then offer ID, so
# the same input always gives the same order.
def rank_offers(offers, request, weights, method="hybrid"):
    if not offers:
        return []

    names = list(CRITERIA)
    raw = {}
    scores = {}
    for name in names:
        crit = CRITERIA[name]
        raw[name] = [crit.raw_value(offer, request) for offer in offers]
        scores[name] = score_criterion(crit, raw[name], method)

    ranked = []
    for position, offer in enumerate(offers):
        offer_raw = {name: raw[name][position] for name in names}
        offer_scores = {name: scores[name][position] for name in names}
        contributions = {name: weights[name] * offer_scores[name] for name in names}
        ranked.append(RankedOffer(offer, offer_raw, offer_scores, contributions,
                                  sum(contributions.values())))

    ranked.sort(key=lambda r: (-round(r.total, 6), r.offer.price_eur,
                               r.offer.departure, r.offer.offer_id))
    for number, item in enumerate(ranked, start=1):
        item.rank = number
    log.info("Ranked %d offers with %s scoring; top offer %s (%.1f)", len(ranked), method,
             ranked[0].offer.offer_id, ranked[0].total)
    return ranked
