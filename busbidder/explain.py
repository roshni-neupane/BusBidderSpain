# Generates a short, data-based explanation of why an offer ranks first.
#
# Strengths are criteria where the offer scores high and the weight is not
# zero; weaknesses are criteria where it scores low. The text always ends by
# saying that the result depends on the traveller's own constraints and weights.

from busbidder.scoring import CRITERIA

STRONG_SCORE = 70           # a score of 70 or more counts as a strength
WEAK_SCORE = 40             # a score below 40 counts as a weakness


def format_minutes(minutes):
    hours, rest = divmod(int(minutes), 60)
    if hours == 0:
        return str(rest) + " min"
    return str(hours) + " h " + "{:02d}".format(rest) + " min"


# Describes one criterion of one offer in words, compared with the other offers.
def describe(name, item, ranked, request):
    offer = item.offer
    values = [other.raw[name] for other in ranked]
    if name == "price":
        cheapest = min(values)
        if offer.price_eur == cheapest:
            return "the lowest price (EUR {:.2f})".format(offer.price_eur)
        return "a price of EUR {:.2f} (EUR {:.2f} above the cheapest acceptable offer)".format(
            offer.price_eur, offer.price_eur - cheapest)
    if name == "duration":
        shortest = min(values)
        text = "a journey of " + format_minutes(offer.duration_minutes)
        if offer.duration_minutes == shortest:
            return text + " (the shortest)"
        return text + " (" + format_minutes(offer.duration_minutes - shortest) + " longer than the shortest)"
    if name == "departure":
        away = item.raw["departure"]
        preferred = request.preferred_departure.strftime("%H:%M")
        if away == 0:
            return "a departure exactly at the preferred time " + preferred
        return ("a departure at " + offer.departure.strftime("%H:%M") + ", "
                + format_minutes(away) + " from the preferred " + preferred)
    if name == "flexibility":
        return "a " + offer.fare.level() + " fare"
    return CRITERIA[name].label.lower()


def join_words(parts):
    if len(parts) == 1:
        return parts[0]
    return ", ".join(parts[:-1]) + " and " + parts[-1]


# Builds the explanation text for the first offer in a ranking.
def explain_top_offer(ranked, request, weights):
    top = ranked[0]
    offer = top.offer

    # Strongest contributions first
    order = sorted(CRITERIA, key=lambda name: -top.contributions[name])
    strengths = [describe(n, top, ranked, request) for n in order
                 if weights[n] > 0 and top.scores[n] >= STRONG_SCORE]
    weaknesses = [describe(n, top, ranked, request) for n in order
                  if weights[n] > 0 and top.scores[n] < WEAK_SCORE]

    lines = []
    headline = (offer.company.name + " " + offer.offer_id + " ranks first with "
                + "{:.1f}".format(top.total) + " points out of 100")
    if len(ranked) > 1:
        gap = top.total - ranked[1].total
        headline = headline + ", " + "{:.1f}".format(gap) + " ahead of " + ranked[1].offer.offer_id
    lines.append(headline + ".")

    if strengths:
        lines.append("Advantages: " + join_words(strengths) + ".")
    if offer.transfers == 0:
        lines.append("It is a direct route.")
    if weaknesses:
        lines.append("Disadvantage: " + join_words(weaknesses) + ".")
    elif len(ranked) > 1:
        lines.append("It has no criterion with a low score among the acceptable offers.")

    lines.append("This is the best match only for this traveller's constraints, weights "
                 "and scoring rules, and only among the " + str(len(ranked))
                 + " offers that passed the hard constraints. It is not objectively the best offer.")
    return " ".join(lines)
