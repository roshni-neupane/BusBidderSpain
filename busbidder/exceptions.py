# Custom exceptions for BusBidder Spain.
#
# All of them inherit from BusBidderError, so the user interface can catch
# every expected problem in one place, while programming errors (such as a
# TypeError) are not hidden.


class BusBidderError(Exception):
    """Base class for all expected problems in BusBidder Spain."""


class DataFileError(BusBidderError):
    """A whole data file cannot be used (missing, unreadable or wrong columns)."""

    def __init__(self, path, reason):
        super().__init__(str(path) + ": " + reason)
        self.path = path
        self.reason = reason


class InvalidRecordError(BusBidderError):
    """One row of a data file cannot be accepted.

    A row can have several problems, so the exception keeps a list of
    (field, reason) pairs.
    """

    def __init__(self, problems):
        parts = [field + ": " + reason for field, reason in problems]
        super().__init__("; ".join(parts))
        self.problems = problems


class UnknownDestinationError(BusBidderError):
    """A traveller asked for a destination that the platform does not serve."""


class InvalidRequestError(BusBidderError):
    """A traveller request has an impossible value (e.g. negative budget)."""


class InvalidWeightsError(BusBidderError):
    """The criterion weights are missing, negative or do not total 100 %."""


class BookingError(BusBidderError):
    """A booking cannot be made (e.g. no seats left or unknown reference)."""
