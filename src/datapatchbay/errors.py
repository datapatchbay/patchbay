"""Exceptions the CLI reports to a user as a message and an exit code."""


class DatapatchbayError(Exception):
    """Base class for failures the CLI turns into a message and a non-zero exit code."""


class RepoNotFoundError(DatapatchbayError):
    """Raised when no `datapatchbay.yaml` exists in the working directory or any parent."""
