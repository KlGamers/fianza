import boa
import pytest

from conftest import DAY, DEP, end_lease

CREATED, ACTIVE, CLAIMED, DISPUTED, SETTLED, CANCELLED = range(1, 7)
WHY = b"broken window".ljust(32, b"\0")


def state(esc, lid):
    return esc.leases(lid).state


def test_constructor_rejects_zero_windows():
    with boa.reverts("windows must be positive"):
        boa.load("contracts/Fianza.vy", 0, 1, 1)


def test_create_validation(esc, who):
    now = boa.env.evm.patch.timestamp
    ll, tn, ar = who["landlord"], who["tenant"], who["arbiter"]
    zero = "0x" + "00" * 20
    with boa.env.prank(ll):
        with boa.reverts("bad tenant"):
            esc.create(zero, ar, DEP, now + DAY)
        with boa.reverts("bad tenant"):
            esc.create(ll, ar, DEP, now + DAY)
        with boa.reverts("bad arbiter"):
            esc.create(tn, zero, DEP, now + DAY)
        with boa.reverts("arbiter must be independent"):
            esc.create(tn, tn, DEP, now + DAY)
        with boa.reverts("arbiter must be independent"):
            esc.create(tn, ll, DEP, now + DAY)
        with boa.reverts("zero amount"):
            esc.create(tn, ar, 0, now + DAY)
        with boa.reverts("ends in the past"):
            esc.create(tn, ar, DEP, now)
        assert esc.create(tn, ar, DEP, now + DAY) == 0
        assert esc.create(tn, ar, DEP, now + DAY) == 1
    assert esc.count() == 2
    lse = esc.leases(0)
    assert (lse.landlord, lse.tenant, lse.arbiter, lse.amount, lse.state) == (ll, tn, ar, DEP, CREATED)


def test_fund_rules(esc, who, lease):
    lid = lease(fund=False)
    with boa.env.prank(who["stranger"]), boa.reverts("only tenant"):
        esc.fund(lid, value=DEP)
    with boa.env.prank(who["tenant"]):
        with boa.reverts("wrong amount"):
            esc.fund(lid, value=DEP - 1)
        esc.fund(lid, value=DEP)
        with boa.reverts("not open for funding"):
            esc.fund(lid, value=DEP)
    assert state(esc, lid) == ACTIVE and esc.locked() == DEP
    assert boa.env.get_balance(esc.address) == DEP

    late = lease(days=1, fund=False)
    end_lease(2)
    with boa.env.prank(who["tenant"]), boa.reverts("lease already ended"):
        esc.fund(late, value=DEP)


def test_cancel(esc, who, lease):
    lid = lease(fund=False)
    with boa.env.prank(who["tenant"]), boa.reverts("only landlord"):
        esc.cancel(lid)
    with boa.env.prank(who["landlord"]):
        esc.cancel(lid)
        with boa.reverts("cannot cancel"):
            esc.cancel(lid)
    assert state(esc, lid) == CANCELLED
    with boa.env.prank(who["tenant"]), boa.reverts("not open for funding"):
        esc.fund(lid, value=DEP)
    with boa.env.prank(who["landlord"]), boa.reverts("cannot cancel"):
        esc.cancel(lease())


def test_release_and_withdraw(esc, who, lease):
    lid = lease()
    with boa.env.prank(who["tenant"]), boa.reverts("only landlord"):
        esc.release(lid)
    with boa.env.prank(who["landlord"]):
        esc.release(lid)
        with boa.reverts("not active"):
            esc.release(lid)
    assert state(esc, lid) == SETTLED and esc.locked() == 0
    assert esc.credit(who["tenant"]) == DEP and esc.credit(who["landlord"]) == 0
    before = boa.env.get_balance(who["tenant"])
    with boa.env.prank(who["tenant"]):
        esc.withdraw()
        with boa.reverts("nothing to withdraw"):
            esc.withdraw()
    assert boa.env.get_balance(who["tenant"]) == before + DEP
    assert boa.env.get_balance(esc.address) == 0


def test_claim_rules(esc, who, lease):
    lid = lease()
    with boa.env.prank(who["landlord"]):
        with boa.reverts("lease not over"):
            esc.claim(lid, DEP // 2, WHY)
        end_lease()
        with boa.reverts("deduction exceeds deposit"):
            esc.claim(lid, DEP + 1, WHY)
    with boa.env.prank(who["tenant"]), boa.reverts("only landlord"):
        esc.claim(lid, 1, WHY)
    with boa.env.prank(who["landlord"]):
        esc.claim(lid, DEP // 4, WHY)
        with boa.reverts("not active"):
            esc.claim(lid, 1, WHY)
    lse = esc.leases(lid)
    assert (lse.state, lse.deduct, lse.reason) == (CLAIMED, DEP // 4, WHY)

    late = lease()
    end_lease(366 + 14)
    with boa.env.prank(who["landlord"]), boa.reverts("claim window closed"):
        esc.claim(late, 1, WHY)


def test_zero_claim_refunds(esc, who, lease):
    lid = lease()
    end_lease()
    with boa.env.prank(who["landlord"]):
        esc.claim(lid, 0, WHY)
    assert state(esc, lid) == SETTLED and esc.credit(who["tenant"]) == DEP


def test_accept(esc, who, lease):
    lid = lease()
    end_lease()
    with boa.env.prank(who["landlord"]):
        esc.claim(lid, DEP // 4, WHY)
        with boa.reverts("only tenant"):
            esc.accept(lid)
    with boa.env.prank(who["tenant"]):
        esc.accept(lid)
        done = esc.get_logs()[-1]
        with boa.reverts("nothing to accept"):
            esc.accept(lid)
    assert esc.credit(who["landlord"]) == DEP // 4
    assert esc.credit(who["tenant"]) == DEP - DEP // 4
    assert type(done).__name__ == "Settled" and done.how == 2


def test_dispute_and_resolve(esc, who, lease):
    lid = lease()
    end_lease()
    with boa.env.prank(who["landlord"]):
        esc.claim(lid, DEP // 2, WHY)
    with boa.env.prank(who["stranger"]), boa.reverts("only tenant"):
        esc.dispute(lid)
    with boa.env.prank(who["tenant"]):
        esc.dispute(lid)
        with boa.reverts("nothing to dispute"):
            esc.dispute(lid)
    assert state(esc, lid) == DISPUTED
    with boa.env.prank(who["landlord"]), boa.reverts("only arbiter"):
        esc.resolve(lid, DEP // 2)
    with boa.env.prank(who["arbiter"]):
        with boa.reverts("award exceeds claim"):
            esc.resolve(lid, DEP // 2 + 1)
        esc.resolve(lid, DEP // 5)
        with boa.reverts("not disputed"):
            esc.resolve(lid, 0)
    assert esc.credit(who["landlord"]) == DEP // 5
    assert esc.credit(who["tenant"]) == DEP - DEP // 5
    assert esc.credit(who["arbiter"]) == 0


def test_reply_and_ruling_windows(esc, who, lease):
    lid = lease()
    end_lease()
    with boa.env.prank(who["landlord"]):
        esc.claim(lid, DEP // 2, WHY)
    boa.env.time_travel(seconds=7 * DAY)
    with boa.env.prank(who["tenant"]), boa.reverts("reply window closed"):
        esc.dispute(lid)

    two = lease()
    end_lease()
    with boa.env.prank(who["landlord"]):
        esc.claim(two, DEP // 2, WHY)
    with boa.env.prank(who["tenant"]):
        esc.dispute(two)
    boa.env.time_travel(seconds=14 * DAY)
    with boa.env.prank(who["arbiter"]), boa.reverts("ruling window closed"):
        esc.resolve(two, 0)


def test_finalize_paths(esc, who, lease):
    quiet, claimed, stuck, early = lease(), lease(), lease(), lease(days=400)
    end_lease()
    with boa.env.prank(who["landlord"]):
        esc.claim(claimed, DEP // 4, WHY)
        esc.claim(stuck, DEP // 2, WHY)
    with boa.env.prank(who["tenant"]):
        esc.dispute(stuck)
    with boa.env.prank(who["stranger"]):
        for lid, msg in ((quiet, "claim window open"), (claimed, "reply window open"), (stuck, "ruling window open")):
            with boa.reverts(msg):
                esc.finalize(lid)
        boa.env.time_travel(seconds=14 * DAY)
        esc.finalize(quiet)
        esc.finalize(claimed)
        esc.finalize(stuck)
        with boa.reverts("nothing to finalize"):
            esc.finalize(quiet)
        with boa.reverts("nothing to finalize"):
            esc.finalize(999)
        with boa.reverts("claim window open"):
            esc.finalize(early)
    assert esc.credit(who["landlord"]) == DEP // 4 + DEP // 4
    assert esc.credit(who["tenant"]) == DEP + (DEP - DEP // 4) + (DEP - DEP // 4)
    assert esc.locked() == DEP
    assert boa.env.get_balance(esc.address) == 4 * DEP


def test_reentrancy_is_blocked(esc, who):
    thief = boa.load("tests/Thief.vy", esc.address)
    boa.env.set_balance(thief.address, 0)
    now = boa.env.evm.patch.timestamp
    with boa.env.prank(who["landlord"]):
        lid = esc.create(thief.address, who["arbiter"], DEP, now + 365 * DAY)
    victim = boa.env.generate_address("victim")
    boa.env.set_balance(victim, 10 * DEP)
    with boa.env.prank(who["landlord"]):
        other = esc.create(victim, who["arbiter"], 5 * DEP, now + 365 * DAY)
    with boa.env.prank(victim):
        esc.fund(other, value=5 * DEP)
    boa.env.set_balance(boa.env.eoa, DEP)
    thief.fund(lid, value=DEP)
    with boa.env.prank(who["landlord"]):
        esc.release(lid)
    with boa.reverts():
        thief.steal()
    assert boa.env.get_balance(esc.address) == 6 * DEP
    assert esc.credit(thief.address) == DEP
    assert boa.env.get_balance(thief.address) == 0


def test_events(esc, who, lease):
    lid = lease(fund=False)
    created = esc.get_logs()[-1]
    assert type(created).__name__ == "Created"
    assert created.tenant == who["tenant"] and created.amount == DEP
    with boa.env.prank(who["tenant"]):
        esc.fund(lid, value=DEP)
    assert type(esc.get_logs()[-1]).__name__ == "Funded"
    end_lease()
    with boa.env.prank(who["landlord"]):
        esc.claim(lid, 7, WHY)
    claim = esc.get_logs()[-1]
    assert type(claim).__name__ == "Claimed" and claim.deduct == 7
    with boa.env.prank(who["tenant"]):
        esc.accept(lid)
        esc.withdraw()
        out = esc.get_logs()[-1]
    assert type(out).__name__ == "Withdrawn" and out.amount == DEP - 7


@pytest.mark.parametrize("amount", [1, 3, 10**30])
def test_odd_amounts_conserve_value(esc, who, lease, amount):
    boa.env.set_balance(who["tenant"], amount * 2)
    lid = lease(amount=amount)
    end_lease()
    with boa.env.prank(who["landlord"]):
        esc.claim(lid, amount, WHY)
    with boa.env.prank(who["tenant"]):
        esc.dispute(lid)
    boa.env.time_travel(seconds=14 * DAY)
    esc.finalize(lid)
    assert esc.credit(who["landlord"]) + esc.credit(who["tenant"]) == amount
    assert esc.credit(who["landlord"]) == amount // 2
