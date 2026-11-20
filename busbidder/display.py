# Text formatting for the command-line interface and the saved outputs.

from busbidder.constraints import HARD_CONSTRAINTS
from busbidder.explain import format_minutes
from busbidder.scoring import CRITERIA

LINE = "-" * 124


def format_request(profile):
    request = profile.request
    lines = [
        profile.name + " - " + profile.description,
        "Journey:              Madrid to " + request.destination.name,
        "Travel window:        " + request.earliest_date.strftime("%d %B") + " to "
        + request.latest_date.strftime("%d %B %Y"),
        "HARD constraints:     budget at most EUR {:.2f}, at most {} transfer(s), changeable ticket {}".format(
            request.max_budget_eur, request.max_transfers,
            "required" if request.changeable_required else "not required"),
        "SOFT preferences:     departure near " + request.preferred_departure.strftime("%H:%M"),
        "Weights:              " + ", ".join(
            CRITERIA[name].label + " " + "{:g}".format(weight * 100) + " %"
            for name, weight in profile.weights.items()),
    ]
    return "\n".join(lines)


def format_filter_summary(result, total):
    lines = ["Hard constraints: " + str(total) + " valid offers checked, "
             + str(len(result.accepted)) + " acceptable."]
    for constraint in HARD_CONSTRAINTS:
        count = len(result.removed[constraint.name])
        lines.append("  removed {:>4}  {}".format(count, constraint.removed_reason))
    return "\n".join(lines)


def format_ranking(ranked, limit=None):
    header = "{:>4} {:<16} {:<15} {:<11} {:>6} {:>8} {:>5} {:<25} | {:>5} {:>5} {:>5} {:>5} | {:>5}".format(
        "Rank", "Offer", "Company", "Departure", "Price", "Duration", "Trans", "Fare",
        "Price", "Dur.", "Dep.", "Flex", "TOTAL")
    lines = [" " * 94 + "criterion scores (0-100)", header, LINE]
    shown = ranked if limit is None else ranked[:limit]
    for item in shown:
        offer = item.offer
        lines.append("{:>4} {:<16} {:<15} {:<11} {:>6.2f} {:>8} {:>5} {:<25} | {:>5.0f} {:>5.0f} {:>5.0f} {:>5.0f} | {:>5.1f}".format(
            item.rank, offer.offer_id, offer.company.name, offer.departure.strftime("%d/%m %H:%M"),
            offer.price_eur, format_minutes(offer.duration_minutes).replace(" min", "m").replace(" h ", "h"),
            offer.transfers, offer.fare.level(),
            item.scores["price"], item.scores["duration"], item.scores["departure"],
            item.scores["flexibility"], item.total))
    if limit is not None and len(ranked) > limit:
        lines.append("     ... " + str(len(ranked) - limit) + " more offers")
    return "\n".join(lines)
