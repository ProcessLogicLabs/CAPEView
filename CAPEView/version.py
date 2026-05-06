"""Version management for CAPEView.

The fallback version is updated by CI on tagged releases (release.yml replaces
__fallback_version__ before running PyInstaller). For dev runs, this is the
authoritative version string.
"""

__fallback_version__ = "v0.0.4"


def get_version() -> str:
    """Return the application version string, e.g. 'v0.0.1'."""
    return __fallback_version__


__version__ = get_version()
