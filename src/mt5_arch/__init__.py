"""MetaTrader 5 integration for Arch Linux via Wine + mt5linux/RPyC."""

from mt5_arch.client import MT5ArchClient
from mt5_arch.config import Settings
from mt5_arch.models import AccountInfo, Candle, CandlesResult, Deal, SymbolInfo, TerminalInfo

__version__ = "0.1.0"

__all__ = [
    "AccountInfo",
    "Candle",
    "CandlesResult",
    "Deal",
    "MT5ArchClient",
    "Settings",
    "SymbolInfo",
    "TerminalInfo",
    "__version__",
]
