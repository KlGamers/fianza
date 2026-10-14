import boa
from boa import BoaError
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from conftest import DAY, WHO_NAMES

OPS = st.one_of(
    st.tuples(st.just("create"), st.integers(1, 10**20), st.integers(1, 30)),
    st.tuples(st.just("fund"), st.integers(0, 50)),
    st.tuples(st.just("cancel"), st.integers(0, 50)),
    st.tuples(st.just("release"), st.integers(0, 50)),
    st.tuples(st.just("claim"), st.integers(0, 50), st.integers(0, 10**20)),
    st.tuples(st.just("accept"), st.integers(0, 50)),
    st.tuples(st.just("dispute"), st.integers(0, 50)),
    st.tuples(st.just("resolve"), st.integers(0, 50), st.integers(0, 10**20)),
    st.tuples(st.just("finalize"), st.integers(0, 50)),
    st.tuples(st.just("withdraw"), st.sampled_from(WHO_NAMES)),
    st.tuples(st.just("wait"), st.integers(1, 20)),
)


@settings(max_examples=200, deadline=None, suppress_health_check=[HealthCheck.function_scoped_fixture])
@given(st.lists(OPS, min_size=10, max_size=60))
def test_value_is_conserved(ops):
    with boa.env.anchor():
        who = {}
        for name in WHO_NAMES:
            who[name] = boa.env.generate_address(name)
            boa.env.set_balance(who[name], 10**24)
        esc = boa.load("contracts/Fianza.vy", 3 * DAY, 2 * DAY, 2 * DAY)
        paid = {n: 0 for n in WHO_NAMES}
        for op in ops:
            kind = op[0]
            if kind not in ("create", "withdraw", "wait"):
                op = (kind, op[1] % max(esc.count(), 1), *op[2:])
            try:
                if kind == "create":
                    with boa.env.prank(who["landlord"]):
                        esc.create(who["tenant"], who["arbiter"], op[1], boa.env.evm.patch.timestamp + op[2] * DAY)
                elif kind == "fund":
                    amt = esc.leases(op[1]).amount
                    with boa.env.prank(who["tenant"]):
                        esc.fund(op[1], value=amt)
                elif kind in ("cancel", "release"):
                    with boa.env.prank(who["landlord"]):
                        getattr(esc, kind)(op[1])
                elif kind == "claim":
                    with boa.env.prank(who["landlord"]):
                        amt = esc.leases(op[1]).amount
                        esc.claim(op[1], op[2] % (amt + 1), b"\x01" * 32)
                elif kind in ("accept", "dispute"):
                    with boa.env.prank(who["tenant"]):
                        getattr(esc, kind)(op[1])
                elif kind == "resolve":
                    with boa.env.prank(who["arbiter"]):
                        esc.resolve(op[1], op[2] % (esc.leases(op[1]).deduct + 1))
                elif kind == "finalize":
                    esc.finalize(op[1])
                elif kind == "withdraw":
                    amt = esc.credit(who[op[1]])
                    with boa.env.prank(who[op[1]]):
                        esc.withdraw()
                    paid[op[1]] += amt
                elif kind == "wait":
                    boa.env.time_travel(seconds=op[1] * DAY)
            except BoaError:
                pass
            held = sum(esc.credit(a) for a in who.values())
            assert boa.env.get_balance(esc.address) == esc.locked() + held
            for i in range(esc.count()):
                lse = esc.leases(i)
                assert lse.deduct <= lse.amount
        assert esc.credit(who["arbiter"]) == 0 and esc.credit(who["stranger"]) == 0
        assert paid["arbiter"] == 0 and paid["stranger"] == 0
