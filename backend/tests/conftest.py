import pandas as pd
import pytest


@pytest.fixture
def dates():
    return pd.date_range("2024-01-01", periods=5, freq="D")


@pytest.fixture
def prices(dates):
    """Two holdings with deliberately different price scales.

    AAPL trades near $10 with a large share count; BRKA near $2,000 with a tiny
    one. Any calculation that ignores share counts will be dominated by BRKA.
    """
    return pd.DataFrame(
        {
            "AAPL": [10.0, 11.0, 12.0, 11.0, 13.0],
            "BRKA": [2000.0, 2010.0, 2020.0, 2015.0, 2030.0],
        },
        index=dates,
    )


@pytest.fixture
def shares():
    return {"AAPL": 500.0, "BRKA": 1.0}


@pytest.fixture
def cost_basis():
    return {"AAPL": 9.0, "BRKA": 1900.0}
