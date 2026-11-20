# Experiments that produce the evidence used in the report.
#
#   E1  the same offers ranked for each traveller profile
#   E2  first scoring version (min-max for all) compared with the final one
#   E3  weight sensitivity: how much must one weight change before the
#       winner changes?
#   E4  an extreme value: one unusual offer added to the acceptable set
#   E5  effective influence of each criterion compared with its weight
#   E6  data validation summary
#
# Results are written to output/experiments.md and, for every profile and
# scoring method, to output/rankings/<profile>_<method>.csv.

import copy
import csv
from collections import Counter
from datetime import timedelta
from pathlib import Path

from busbidder.constraints import filter_offers
from busbidder.scoring import CRITERIA, METHODS, rank_offers


def acceptable_offers(market, profile):
    return filter_offers(list(market.offers.values()), profile.request).accepted


def short(item):
    offer = item.offer
    return "{} ({}, {}, EUR {:.2f}, {} fare)".format(
        offer.offer_id, offer.company.name, offer.departure.strftime("%d/%m %H:%M"),
        offer.price_eur, offer.fare.level())


def table(header, rows):
    lines = ["| " + " | ".join(header) + " |", "|" + "|".join("---" for _ in header) + "|"]
    for row in rows:
        lines.append("| " + " | ".join(str(cell) for cell in row) + " |")
    return "\n".join(lines)


# Moves one weight by `change` percentage points and scales the others so
# that the total stays 100 %. Returns None if the weight would leave 0-100.
def shifted_weights(weights, name, change):
    new_value = weights[name] + change / 100
    if new_value < 0 or new_value > 1:
        return None
    others = {n: w for n, w in weights.items() if n != name}
    others_total = sum(others.values())
    if others_total == 0:
        return None
    result = {n: w * (1 - new_value) / others_total for n, w in others.items()}
    result[name] = new_value
    return result


def write_ranking_csv(path, ranked):
    names = list(CRITERIA)
    with open(path, "w", encoding="utf-8", newline="") as file:
        writer = csv.writer(file)
        writer.writerow(["rank", "offer_id", "company", "departure", "price_eur", "duration_min",
                         "transfers", "fare"] + ["raw_" + n for n in names]
                        + ["score_" + n for n in names] + ["points_" + n for n in names] + ["total"])
        for item in ranked:
            offer = item.offer
            writer.writerow([item.rank, offer.offer_id, offer.company.name,
                             offer.departure.strftime("%Y-%m-%d %H:%M"), "{:.2f}".format(offer.price_eur),
                             offer.duration_minutes, offer.transfers, offer.fare.level()]
                            + [item.raw[n] for n in names]
                            + ["{:.1f}".format(item.scores[n]) for n in names]
                            + ["{:.1f}".format(item.contributions[n]) for n in names]
                            + ["{:.1f}".format(item.total)])


def experiment_profiles(market, profiles):
    rows = []
    for profile in profiles.values():
        ranked = rank_offers(acceptable_offers(market, profile), profile.request, profile.weights)
        margin = ranked[0].total - ranked[1].total if len(ranked) > 1 else 0
        rows.append([profile.name, len(ranked), short(ranked[0]), "{:.1f}".format(ranked[0].total),
                     "{:.1f}".format(margin), short(ranked[1]) if len(ranked) > 1 else "-"])
    return ("## E1 Same offers, different travellers\n\n"
            "All profiles search Madrid to Malaga, 12-14 July, among the same "
            + str(len(market.offers)) + " valid offers (final hybrid scoring).\n\n"
            + table(["Profile", "Acceptable offers", "Rank 1", "Total", "Lead over rank 2", "Rank 2"], rows))


def experiment_methods(market, profiles):
    rows = []
    for profile in profiles.values():
        offers = acceptable_offers(market, profile)
        first = rank_offers(offers, profile.request, profile.weights, "minmax")
        final = rank_offers(offers, profile.request, profile.weights, "hybrid")
        positions_first = {item.offer.offer_id: item.rank for item in first}
        moved = sum(1 for item in final if positions_first[item.offer.offer_id] != item.rank)
        rows.append([profile.name, short(first[0]), short(final[0]),
                     "yes" if first[0].offer is not final[0].offer else "no",
                     str(moved) + " of " + str(len(final))])
    return ("## E2 First scoring version (min-max for all criteria) compared with the final version\n\n"
            "Final version: min-max for price and duration; fixed scales for departure "
            "(100 at the preferred time, 0 at 6 hours away) and flexibility (0 / 60 / 100).\n\n"
            + table(["Profile", "Rank 1 with min-max for all", "Rank 1 final", "Winner changed",
                     "Offers that changed position"], rows))


def experiment_sensitivity(market, profiles):
    sections = ["## E3 Weight sensitivity\n\n"
                "Each weight is moved up or down in steps of 1 percentage point; the other "
                "weights are scaled so the total stays 100 %. The table shows the smallest "
                "change that gives a different rank-1 offer (\"-\" = no change within the allowed range)."]
    for profile in profiles.values():
        offers = acceptable_offers(market, profile)
        base = rank_offers(offers, profile.request, profile.weights)
        rows = []
        for name in CRITERIA:
            cells = [CRITERIA[name].label, "{:g} %".format(profile.weights[name] * 100)]
            for direction in (1, -1):
                found = "-"
                for step in range(1, 101):
                    weights = shifted_weights(profile.weights, name, direction * step)
                    if weights is None:
                        break
                    winner = rank_offers(offers, profile.request, weights)[0]
                    if winner.offer is not base[0].offer:
                        found = "{:+d} points -> {}".format(direction * step, winner.offer.offer_id)
                        break
                cells.append(found)
            rows.append(cells)
        sections.append("### " + profile.name + " (rank 1: " + base[0].offer.offer_id + ")\n\n"
                        + table(["Criterion", "Weight", "Smallest increase that changes rank 1",
                                 "Smallest decrease that changes rank 1"], rows))
    return "\n\n".join(sections)


def experiment_extreme_value(market, profiles):
    profile = profiles.get("budget") or next(iter(profiles.values()))
    offers = acceptable_offers(market, profile)
    before = rank_offers(offers, profile.request, profile.weights)

    # A very cheap but very slow offer that still meets every hard constraint
    extreme = copy.copy(before[0].offer)
    extreme.offer_id = "SOL-MAL-0713-99"
    extreme.price_eur = 12.00
    extreme.arrival = extreme.departure + timedelta(hours=14)
    extreme.fare = copy.copy(extreme.fare)
    after = rank_offers(offers + [extreme], profile.request, profile.weights)

    rows = []
    for item in before:
        later = next(a for a in after if a.offer is item.offer)
        rows.append([item.offer.offer_id, "{:.2f}".format(item.offer.price_eur),
                     "{:.0f}".format(item.scores["price"]), "{:.0f}".format(later.scores["price"]),
                     "{:.0f}".format(item.scores["duration"]), "{:.0f}".format(later.scores["duration"]),
                     item.rank, later.rank])
    return ("## E4 Extreme value\n\n"
            "An artificial offer (EUR 12.00, 14 hours, otherwise like " + before[0].offer.offer_id
            + ") is added for the " + profile.name.lower() + ". It ranks "
            + str(next(a.rank for a in after if a.offer is extreme)) + " of " + str(len(after))
            + ". The other offers' min-max scores change although they themselves did not change.\n\n"
            + table(["Offer", "Price", "Price score before", "Price score after", "Duration score before",
                     "Duration score after", "Rank before", "Rank after"], rows))


def experiment_influence(market, profiles):
    sections = ["## E5 Effective influence of each criterion\n\n"
                "For each criterion: the spread (highest minus lowest) of the points it adds to the "
                "total among the acceptable offers, and its share of all spreads. A criterion with a "
                "large weight but a small spread hardly affects the order."]
    for profile in profiles.values():
        ranked = rank_offers(acceptable_offers(market, profile), profile.request, profile.weights)
        spreads = {}
        for name in CRITERIA:
            points = [item.contributions[name] for item in ranked]
            spreads[name] = max(points) - min(points)
        total = sum(spreads.values()) or 1
        rows = [[CRITERIA[n].label, "{:g} %".format(profile.weights[n] * 100),
                 "{:.1f}".format(spreads[n]), "{:.0f} %".format(100 * spreads[n] / total)] for n in CRITERIA]
        sections.append("### " + profile.name + "\n\n"
                        + table(["Criterion", "Weight", "Spread of points", "Share of influence"], rows))
    return "\n\n".join(sections)


def experiment_validation(market):
    reasons = Counter(item["field"] for item in market.review_queue)
    rows = [[field, count] for field, count in sorted(reasons.items())]
    rows_set_aside = len({(i["file"], i["row"]) for i in market.review_queue})
    sold_out = sum(1 for offer in market.offers.values() if offer.seats_available == 0)
    return ("## E6 Data validation\n\n"
            "Valid offers loaded: " + str(len(market.offers)) + ". Rows set aside for review: "
            + str(rows_set_aside) + " (problems: " + str(len(market.review_queue)) + "). "
            "Automatic corrections: " + str(len(market.corrections)) + ". Valid but sold-out offers: "
            + str(sold_out) + " (kept, removed later by the seat constraint).\n\n"
            + table(["Field with a problem", "Number of problems"], rows))


def run_experiments(market, profiles, output_folder):
    folder = Path(output_folder)
    (folder / "rankings").mkdir(parents=True, exist_ok=True)
    written = []
    for profile in profiles.values():
        offers = acceptable_offers(market, profile)
        for method in METHODS:
            path = folder / "rankings" / (profile.key + "_" + method + ".csv")
            write_ranking_csv(path, rank_offers(offers, profile.request, profile.weights, method))
            written.append(path)

    parts = ["# BusBidder Spain - experiment results",
             "Produced by `python main.py experiments`. The data and the ranking are deterministic, "
             "so running the command again gives the same results.",
             experiment_profiles(market, profiles), experiment_methods(market, profiles),
             experiment_sensitivity(market, profiles), experiment_extreme_value(market, profiles),
             experiment_influence(market, profiles), experiment_validation(market)]
    report = folder / "experiments.md"
    with open(report, "w", encoding="utf-8") as file:
        file.write("\n\n".join(parts) + "\n")
    written.insert(0, report)
    return written
