# Checks and converts the text values read from the data files.
#
# Each function either returns a converted value or raises
# InvalidRecordError naming the field and the reason.

import re
from datetime import datetime, time

from busbidder.exceptions import InvalidRecordError
from busbidder.models import NAMED_TIMES

# Offer IDs look like SOL-MAL-0712-01: company, destination, month+day, number.
# The named groups let us check that the ID agrees with the other columns.
OFFER_ID_PATTERN = re.compile(r"(?P<company>[A-Z]{3})-(?P<destination>[A-Z]{3})-(?P<monthday>\d{4})-(?P<number>\d{2})")

# Company and destination codes: three capital letters
CODE_PATTERN = re.compile(r"[A-Z]{3}")

# A clock time such as 08:30
TIME_PATTERN = re.compile(r"([01]\d|2[0-3]):([0-5]\d)")

DATETIME_FORMAT = "%Y-%m-%d %H:%M"
RATING_SCALE = (1.0, 5.0)


def _problem(field, reason):
    return InvalidRecordError([(field, reason)])


def require(field, text):
    if text is None or text.strip() == "":
        raise _problem(field, "value is missing")
    return text.strip()


def parse_offer_id(text):
    text = require("offer_id", text)
    match = OFFER_ID_PATTERN.fullmatch(text)
    if match is None:
        raise _problem("offer_id", "'" + text + "' does not have the format AAA-BBB-MMDD-NN")
    return text, match


def parse_code(field, text):
    text = require(field, text)
    if CODE_PATTERN.fullmatch(text) is None:
        raise _problem(field, "'" + text + "' is not a three-letter code")
    return text


def parse_datetime(field, text):
    text = require(field, text)
    try:
        return datetime.strptime(text, DATETIME_FORMAT)
    except ValueError:
        raise _problem(field, "'" + text + "' is not a valid date and time (YYYY-MM-DD HH:MM)")


def parse_number(field, text, lowest=None, highest=None):
    text = require(field, text)
    try:
        value = float(text)
    except ValueError:
        raise _problem(field, "'" + text + "' is not a number")
    if lowest is not None and not value >= lowest:      # also rejects "nan"
        raise _problem(field, text + " is below the lowest allowed value " + "{:g}".format(lowest))
    if highest is not None and not value <= highest:
        raise _problem(field, text + " is above the highest allowed value " + "{:g}".format(highest))
    return value


def parse_whole_number(field, text, lowest=0):
    text = require(field, text)
    try:
        value = int(text)
    except ValueError:
        raise _problem(field, "'" + text + "' is not a whole number")
    if value < lowest:
        raise _problem(field, text + " is below the lowest allowed value " + str(lowest))
    return value


def parse_yes_no(field, text):
    text = require(field, text).lower()
    if text not in ("yes", "no"):
        raise _problem(field, "'" + text + "' must be yes or no")
    return text == "yes"


# Turns "morning" or "08:30" into a time object.
def parse_preferred_time(text):
    text = str(text).strip().lower()
    if text in NAMED_TIMES:
        return NAMED_TIMES[text]
    match = TIME_PATTERN.fullmatch(text)
    if match is None:
        raise _problem("preferred_departure", "'" + text + "' must be HH:MM or one of "
                       + ", ".join(NAMED_TIMES))
    return time(int(match.group(1)), int(match.group(2)))


def check_row_length(row, columns):
    if None in row:
        raise _problem("row", "expected " + str(len(columns)) + " values but found "
                       + str(len(columns) + len(row[None])))
    for column in columns:
        if row.get(column) is None:
            found = len([c for c in columns if row.get(c) is not None])
            raise _problem("row", "expected " + str(len(columns)) + " values but found " + str(found))


# Checks one offer row and returns its converted values.
# All problems in the row are collected and raised together.
def validate_offer_row(row, companies, destinations):
    problems = []
    values = {}

    def attempt(key, function, *arguments):
        try:
            values[key] = function(*arguments)
        except InvalidRecordError as error:
            problems.extend(error.problems)

    attempt("offer", parse_offer_id, row["offer_id"])
    attempt("company_id", parse_code, "company_id", row["company_id"])
    attempt("destination_id", parse_code, "destination_id", row["destination_id"])
    attempt("departure", parse_datetime, "departure", row["departure"])
    attempt("arrival", parse_datetime, "arrival", row["arrival"])
    attempt("price_eur", parse_number, "price_eur", row["price_eur"], 0.01)
    attempt("transfers", parse_whole_number, "transfers", row["transfers"])
    attempt("luggage_kg", parse_number, "luggage_kg", row["luggage_kg"], 0)
    attempt("changeable", parse_yes_no, "changeable", row["changeable"])
    attempt("refundable", parse_yes_no, "refundable", row["refundable"])
    attempt("seats_available", parse_whole_number, "seats_available", row["seats_available"])
    attempt("rating", parse_number, "rating", row["rating"], RATING_SCALE[0], RATING_SCALE[1])
    if row["co2_kg"].strip() == "":
        values["co2_kg"] = None                     # optional: unknown emissions
    else:
        attempt("co2_kg", parse_number, "co2_kg", row["co2_kg"], 0)

    # Checks between fields, only when the single values were valid
    if "company_id" in values and values["company_id"] not in companies:
        problems.append(("company_id", "unknown company '" + values["company_id"] + "'"))
    if "destination_id" in values and values["destination_id"] not in destinations:
        problems.append(("destination_id", "unknown destination '" + values["destination_id"] + "'"))
    if "departure" in values and "arrival" in values and values["arrival"] <= values["departure"]:
        problems.append(("arrival", "arrival " + row["arrival"].strip()
                         + " is not after departure " + row["departure"].strip()))
    if values.get("refundable") and values.get("changeable") is False:
        problems.append(("refundable", "a refundable fare must also be changeable"))
    if "offer" in values:
        offer_id, match = values["offer"]
        values["offer_id"] = offer_id
        if "company_id" in values and match.group("company") != values["company_id"]:
            problems.append(("offer_id", "ID company " + match.group("company")
                             + " does not match company_id " + values["company_id"]))
        if "destination_id" in values and match.group("destination") != values["destination_id"]:
            problems.append(("offer_id", "ID destination " + match.group("destination")
                             + " does not match destination_id " + values["destination_id"]))

    if problems:
        raise InvalidRecordError(problems)
    return values
