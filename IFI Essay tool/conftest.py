"""Pytest hooks for IFI Essay tool. Remind to set Google credentials in this terminal session."""

import os


def pytest_configure(config):
    """Remind to set GOOGLE_APPLICATION_CREDENTIALS at the start of each terminal session."""
    if not os.environ.get("GOOGLE_APPLICATION_CREDENTIALS"):
        print(
            "\nTip: Export credentials for this session (use the key JSON or a file path): "
            "export GOOGLE_APPLICATION_CREDENTIALS='{\"type\":\"service_account\",...}'  or  source scripts/set_google_credentials.sh\n",
            end="",
        )
