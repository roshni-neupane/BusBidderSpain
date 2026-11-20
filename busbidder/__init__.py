# BusBidder Spain - a flexible bus-booking and weighted offer-ranking platform.
#
# The package logger has a NullHandler, so nothing is printed unless the
# application configures logging (see logging_setup.py). Tests stay quiet.

import logging

logging.getLogger("busbidder").addHandler(logging.NullHandler())
