"""Published document versions; update these whenever the corresponding text changes."""
TERMS_VERSION = "2026-10-23.2"
PRIVACY_VERSION = "2026-10-23.6"


def accepted_current_documents(data):
    return (data.get("legal_accepted") == "yes"
            and data.get("terms_version") == TERMS_VERSION
            and data.get("privacy_version") == PRIVACY_VERSION)
