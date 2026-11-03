"""NotePDF: add highlights and comments to PDFs from a config file or from LaTeX revision markers."""

from .apply import Report, apply, collect_entries
from .config import Config, ConfigError

__version__ = "0.1.0"
__all__ = ["Config", "ConfigError", "Report", "apply", "collect_entries", "__version__"]
