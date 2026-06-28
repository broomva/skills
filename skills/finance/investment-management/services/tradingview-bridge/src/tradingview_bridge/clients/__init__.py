"""Broker clients — concrete implementations of the BrokerClient ABC.

PR 2: MockClient is the only client tests actually exercise. IBKR / Kraken /
Polymarket clients ship as skeletons that raise NotConfiguredError outside
mock mode — the abstraction is complete; real-paper integration follows in
PR 2b once broker credentials are provisioned.
"""

from .base import BrokerClient, NotConfiguredError, OrderReceipt
from .ibkr import IBKRClient
from .kraken import KrakenClient
from .mock import MockClient
from .polymarket import PolymarketClient
from .tradingview_paper import TradingViewPaperClient

__all__ = [
    "BrokerClient",
    "IBKRClient",
    "KrakenClient",
    "MockClient",
    "NotConfiguredError",
    "OrderReceipt",
    "PolymarketClient",
    "TradingViewPaperClient",
]
