"""Pure-math analytics core: portfolio returns, risk, concentration, credit models.

Nothing in this package performs I/O. Providers fetch data and hand plain
pandas objects in, which keeps every calculation here testable offline.
"""

from app.analytics import concentration, credit, returns, risk

__all__ = ["concentration", "credit", "returns", "risk"]
