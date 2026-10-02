"""Importing this package registers every builtin detector."""
from app.detectors.builtin import (  # noqa: F401
    dau_change, dau_increase, holiday_usage, stale_data, token_spike, tokens_per_user,
)
