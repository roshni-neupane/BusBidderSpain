# Loads the data files and builds the Marketplace.
#
# Policy for problem rows (explained in the report):
#   - small format slips in codes (e.g. " mal ") are CORRECTED and logged;
#   - every other invalid row is PLACED ASIDE FOR REVIEW: it is not used,
#     it is written to output/review_queue.csv and logged as a warning;
#   - a sold-out offer (0 seats) is valid data: it is kept, and the seat
#     constraint removes it before ranking.

import csv
import json
import logging
from datetime import date
from pathlib import Path

from busbidder.exceptions import (BusBidderError, DataFileError, InvalidRecordError,
                                  UnknownDestinationError)
from busbidder.models import (Company, Destination, FareConditions, Offer, TravelRequest,
                              TravellerProfile)
from busbidder.validation import check_row_length, parse_preferred_time, validate_offer_row

log = logging.getLogger("busbidder")

COMPANY_COLUMNS = ["company_id", "name", "profile"]
DESTINATION_COLUMNS = ["destination_id", "name", "distance_km", "coastal", "major_city"]
OFFER_COLUMNS = ["offer_id", "company_id", "destination_id", "departure", "arrival",
                 "price_eur", "transfers", "luggage_kg", "changeable", "refundable",
                 "seats_available", "rating", "co2_kg"]


# Opens a CSV file, checks the header and returns (line_number, row) pairs.
def read_csv(path, columns):
    path = Path(path)
    rows = []
    try:
        with open(path, encoding="utf-8", newline="") as file:
            reader = csv.DictReader(file)
            if reader.fieldnames is None:
                raise DataFileError(path, "the file is empty")
            missing = [c for c in columns if c not in reader.fieldnames]
            if missing:
                raise DataFileError(path, "missing column(s): " + ", ".join(missing))
            for row in reader:
                rows.append((reader.line_num, row))
    except FileNotFoundError:
        raise DataFileError(path, "the file was not found")
    except (PermissionError, IsADirectoryError):
        raise DataFileError(path, "the file cannot be opened")
    except UnicodeDecodeError:
        raise DataFileError(path, "the file is not UTF-8 text")
    except csv.Error as error:
        raise DataFileError(path, "damaged CSV format (" + str(error) + ")")
    return rows


class Marketplace:
    """All companies, destinations and valid offers, plus the rows set aside."""

    def __init__(self):
        self.companies = {}         # company_id -> Company
        self.destinations = {}      # destination_id -> Destination
        self.offers = {}            # offer_id -> Offer
        self.review_queue = []      # dictionaries: file, row, offer_id, field, reason
        self.corrections = []       # texts describing automatic corrections

    # Reads companies, destinations and one or more offer files from a folder.
    @classmethod
    def load(cls, data_folder, offer_files=("offers.csv", "offers_invalid.csv")):
        market = cls()
        folder = Path(data_folder)
        market.load_companies(folder / "companies.csv")
        market.load_destinations(folder / "destinations.csv")
        for name in offer_files:
            market.load_offers(folder / name)
        log.info("Loaded %d companies, %d destinations, %d valid offers; %d rows set aside",
                 len(market.companies), len(market.destinations), len(market.offers),
                 len({(r["file"], r["row"]) for r in market.review_queue}))
        return market

    def load_companies(self, path):
        for line, row in read_csv(path, COMPANY_COLUMNS):
            code = row["company_id"].strip().upper()
            self.companies[code] = Company(code, row["name"].strip(), row["profile"].strip())

    def load_destinations(self, path):
        for line, row in read_csv(path, DESTINATION_COLUMNS):
            try:
                distance = int(row["distance_km"])
            except ValueError:
                raise DataFileError(path, "row " + str(line) + ": distance_km must be a whole number")
            code = row["destination_id"].strip().upper()
            self.destinations[code] = Destination(code, row["name"].strip(), distance,
                                                  row["coastal"].strip() == "yes",
                                                  row["major_city"].strip() == "yes")

    def set_aside(self, source, line, offer_id, problems):
        for field, reason in problems:
            self.review_queue.append({"file": source, "row": line, "offer_id": offer_id,
                                      "field": field, "reason": reason})
            log.warning("Set aside %s row %d (%s): %s - %s", source, line, offer_id, field, reason)

    # Reads one offer file. Invalid rows are set aside; reading continues.
    def load_offers(self, path):
        source = Path(path).name
        for line, row in read_csv(path, OFFER_COLUMNS):
            offer_id = (row.get("offer_id") or "").strip()
            try:
                check_row_length(row, OFFER_COLUMNS)
                self.correct_codes(row, source, line)
                values = validate_offer_row(row, self.companies, self.destinations)
                if values["offer_id"] in self.offers:
                    raise InvalidRecordError([("offer_id", "duplicate of an offer already loaded")])
            except InvalidRecordError as error:
                self.set_aside(source, line, offer_id, error.problems)
                continue
            self.offers[values["offer_id"]] = self.build_offer(values)

    # Corrects harmless format slips in the two code columns and logs them.
    def correct_codes(self, row, source, line):
        for column in ("company_id", "destination_id"):
            original = row[column]
            corrected = original.strip().upper()
            if corrected != original and corrected != "":
                row[column] = corrected
                message = (source + " row " + str(line) + ": " + column + " '" + original
                           + "' corrected to '" + corrected + "'")
                self.corrections.append(message)
                log.info("Corrected %s", message)

    def build_offer(self, values):
        fare = FareConditions(values["changeable"], values["refundable"], values["luggage_kg"])
        return Offer(values["offer_id"], self.companies[values["company_id"]],
                     self.destinations[values["destination_id"]], values["departure"],
                     values["arrival"], values["price_eur"], values["transfers"], fare,
                     values["seats_available"], values["rating"], values["co2_kg"])

    # Finds a destination by name or code, ignoring capital letters.
    def find_destination(self, text):
        wanted = str(text).strip().lower()
        for destination in self.destinations.values():
            if wanted in (destination.name.lower(), destination.destination_id.lower()):
                return destination
        raise UnknownDestinationError("'" + str(text) + "' is not one of the 15 destinations")

    # Writes the rows set aside for review to a CSV file.
    def write_review_queue(self, path):
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8", newline="") as file:
            writer = csv.DictWriter(file, fieldnames=["file", "row", "offer_id", "field", "reason"])
            writer.writeheader()
            writer.writerows(self.review_queue)
        return path


# Reads the traveller profiles from a JSON file.
# Returns a dictionary: profile key -> TravellerProfile.
def load_profiles(path, market, criterion_names):
    path = Path(path)
    try:
        with open(path, encoding="utf-8") as file:
            data = json.load(file)
    except FileNotFoundError:
        raise DataFileError(path, "the file was not found")
    except json.JSONDecodeError as error:
        raise DataFileError(path, "invalid JSON (" + str(error) + ")")

    profiles = {}
    for key, item in data.items():
        try:
            request_data = item["request"]
            request = TravelRequest(
                destination=market.find_destination(request_data["destination"]),
                earliest_date=date.fromisoformat(request_data["earliest_date"]),
                latest_date=date.fromisoformat(request_data["latest_date"]),
                max_budget_eur=float(request_data["max_budget_eur"]),
                preferred_departure=parse_preferred_time(request_data["preferred_departure"]),
                max_transfers=int(request_data["max_transfers"]),
                changeable_required=bool(request_data["changeable_required"]))
            profiles[key] = TravellerProfile(key, item["name"], item.get("description", ""),
                                             request, item["weights"], criterion_names)
        except KeyError as error:
            raise DataFileError(path, "profile '" + key + "' is missing " + str(error))
        except (ValueError, BusBidderError) as error:
            raise DataFileError(path, "profile '" + key + "': " + str(error))
    return profiles
