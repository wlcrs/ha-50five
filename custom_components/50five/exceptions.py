"""Exceptions for the 50five GraphQL integration."""

from homeassistant.exceptions import HomeAssistantError


class FiftyFiveError(HomeAssistantError):
    """Base exception for 50five errors."""


class FiftyFiveAuthError(FiftyFiveError):
    """Exception for authentication errors."""


class FiftyFiveConnectionError(FiftyFiveError):
    """Exception for connection errors."""


class FiftyFiveApiError(FiftyFiveError):
    """Exception for API errors."""
