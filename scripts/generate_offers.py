# Generates data/offers.csv: simulated bus offers from the five companies.
#
# The data is fictional. A fixed random seed is used, so running the script
# again gives exactly the same file. Run it from the project folder with:
#   python scripts/generate_offers.py

import csv
import random
from datetime import datetime, timedelta
from pathlib import Path

SEED = 2026
FIRST_DATE = datetime(2026, 7, 10)
NUMBER_OF_DAYS = 7                      # 10 to 16 July 2026

DATA_FOLDER = Path(__file__).resolve().parent.parent / "data"

# How each company differs. These values are design choices for the
# simulation, based on the company profiles in the project specification.
#   price_per_km    price level in euros per kilometre
#   speed_kmh       average speed including stops
#   first, last     earliest and latest departure time (hours, 24 = midnight)
#   changeable      chance that a ticket can be changed
#   refundable      chance that a changeable ticket can also be refunded
#   transfer_chance chance of one transfer on longer routes
#   co2_per_km      kg CO2 per passenger per kilometre
COMPANIES = {
    "SOL": {"price_per_km": 0.055, "speed_kmh": 68, "first": 7, "last": 16,
            "changeable": 0.2, "refundable": 0.1, "transfer_chance": 0.6,
            "luggage_kg": 20, "rating": 3.7, "co2_per_km": 0.030},
    "CAM": {"price_per_km": 0.105, "speed_kmh": 88, "first": 6.5, "last": 20,
            "changeable": 0.8, "refundable": 0.5, "transfer_chance": 0.1,
            "luggage_kg": 30, "rating": 4.4, "co2_per_km": 0.032},
    "CST": {"price_per_km": 0.075, "speed_kmh": 78, "first": 7, "last": 19,
            "changeable": 0.5, "refundable": 0.3, "transfer_chance": 0.3,
            "luggage_kg": 25, "rating": 4.0, "co2_per_km": 0.028},
    "VRD": {"price_per_km": 0.085, "speed_kmh": 78, "first": 8, "last": 18,
            "changeable": 0.7, "refundable": 0.7, "transfer_chance": 0.3,
            "luggage_kg": 25, "rating": 4.2, "co2_per_km": 0.014},
    "NOC": {"price_per_km": 0.050, "speed_kmh": 62, "first": 21, "last": 24.5,
            "changeable": 0.4, "refundable": 0.2, "transfer_chance": 0.4,
            "luggage_kg": 30, "rating": 3.8, "co2_per_km": 0.027},
}

COLUMNS = ["offer_id", "company_id", "destination_id", "departure", "arrival",
           "price_eur", "transfers", "luggage_kg", "changeable", "refundable",
           "seats_available", "rating", "co2_kg"]


# Reads the destination file so the generator uses the same 15 destinations.
def read_destinations():
    with open(DATA_FOLDER / "destinations.csv", encoding="utf-8", newline="") as file:
        return list(csv.DictReader(file))


# Number of departures per day for one company and destination.
def departures_per_day(company_id, destination, rng):
    if company_id == "CST" and destination["coastal"] == "yes":
        return 2                         # CostaLink: more coastal departures
    if company_id == "CAM" and destination["major_city"] == "yes":
        return 2                         # Camino Express: frequent major routes
    return rng.choice([1, 1, 2])


# Creates one offer as a dictionary of text values (as in the CSV file).
def make_offer(company_id, destination, day, number, rng):
    settings = COMPANIES[company_id]
    distance = int(destination["distance_km"])

    # Departure time, rounded to 15 minutes
    hour = rng.uniform(settings["first"], settings["last"])
    departure = day + timedelta(minutes=round(hour * 60 / 15) * 15)

    # Transfers: only on routes over 300 km; Camino Express is direct to major cities
    transfers = 0
    if distance > 300 and rng.random() < settings["transfer_chance"]:
        transfers = 1
    if company_id == "CAM" and destination["major_city"] == "yes":
        transfers = 0

    # Duration: distance / speed, plus 40 minutes for a transfer, plus variation
    minutes = distance / settings["speed_kmh"] * 60 + transfers * 40 + rng.uniform(-15, 20)
    arrival = departure + timedelta(minutes=round(minutes / 5) * 5)

    # Price: distance based, cheaper on CostaLink's coastal routes, small variation
    price = distance * settings["price_per_km"] * rng.uniform(0.85, 1.2) + 4
    if company_id == "CST" and destination["coastal"] == "no":
        price = price * 1.15
    price = round(price * 2) / 2         # nearest 0.50 euro

    changeable = rng.random() < settings["changeable"]
    refundable = changeable and rng.random() < settings["refundable"]

    seats = rng.randint(1, 45)
    if rng.random() < 0.05:
        seats = 0                        # about 5 % of departures are sold out

    rating = min(5.0, max(1.0, rng.gauss(settings["rating"], 0.2)))
    co2 = distance * settings["co2_per_km"]
    co2_text = "" if rng.random() < 0.03 else "{:.1f}".format(co2)   # sometimes unknown

    offer_id = "{}-{}-{}-{:02d}".format(company_id, destination["destination_id"],
                                        day.strftime("%m%d"), number)
    return {
        "offer_id": offer_id,
        "company_id": company_id,
        "destination_id": destination["destination_id"],
        "departure": departure.strftime("%Y-%m-%d %H:%M"),
        "arrival": arrival.strftime("%Y-%m-%d %H:%M"),
        "price_eur": "{:.2f}".format(price),
        "transfers": str(transfers),
        "luggage_kg": str(settings["luggage_kg"]),
        "changeable": "yes" if changeable else "no",
        "refundable": "yes" if refundable else "no",
        "seats_available": str(seats),
        "rating": "{:.1f}".format(rating),
        "co2_kg": co2_text,
    }


def main():
    rng = random.Random(SEED)
    offers = []
    for destination in read_destinations():
        for company_id in COMPANIES:
            for day_number in range(NUMBER_OF_DAYS):
                day = FIRST_DATE + timedelta(days=day_number)
                for number in range(1, departures_per_day(company_id, destination, rng) + 1):
                    offers.append(make_offer(company_id, destination, day, number, rng))

    with open(DATA_FOLDER / "offers.csv", "w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=COLUMNS)
        writer.writeheader()
        writer.writerows(offers)
    print("Wrote " + str(len(offers)) + " offers to data/offers.csv")


if __name__ == "__main__":
    main()
