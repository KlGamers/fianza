import boa
import pytest

DAY = 86_400
DEP = 10**18
WHO_NAMES = ("landlord", "tenant", "arbiter", "stranger")


@pytest.fixture(autouse=True)
def iso():
    with boa.env.anchor():
        yield


@pytest.fixture
def who():
    out = {}
    for name in WHO_NAMES:
        addr = boa.env.generate_address(name)
        boa.env.set_balance(addr, 100 * DEP)
        out[name] = addr
    return out


@pytest.fixture
def esc():
    return boa.load("contracts/Fianza.vy", 14 * DAY, 7 * DAY, 14 * DAY)


@pytest.fixture
def lease(esc, who):
    def make(amount=DEP, days=365, fund=True):
        ends = boa.env.evm.patch.timestamp + days * DAY
        with boa.env.prank(who["landlord"]):
            lid = esc.create(who["tenant"], who["arbiter"], amount, ends)
        if fund:
            with boa.env.prank(who["tenant"]):
                esc.fund(lid, value=amount)
        return lid

    return make


def end_lease(days=366):
    boa.env.time_travel(seconds=days * DAY)
