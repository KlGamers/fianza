# pragma version ~=0.4.3

CREATED: constant(uint8) = 1
ACTIVE: constant(uint8) = 2
CLAIMED: constant(uint8) = 3
DISPUTED: constant(uint8) = 4
SETTLED: constant(uint8) = 5
CANCELLED: constant(uint8) = 6


struct Lease:
    landlord: address
    tenant: address
    arbiter: address
    amount: uint256
    ends: uint256
    deduct: uint256
    stamp: uint256
    reason: bytes32
    state: uint8


event Created:
    id: indexed(uint256)
    landlord: indexed(address)
    tenant: indexed(address)
    arbiter: address
    amount: uint256
    ends: uint256


event Funded:
    id: indexed(uint256)
    amount: uint256


event Cancelled:
    id: indexed(uint256)


event Claimed:
    id: indexed(uint256)
    deduct: uint256
    reason: bytes32


event Disputed:
    id: indexed(uint256)


event Settled:
    id: indexed(uint256)
    to_landlord: uint256
    to_tenant: uint256
    how: uint8


event Withdrawn:
    who: indexed(address)
    amount: uint256


CLAIM_WIN: public(immutable(uint256))
REPLY_WIN: public(immutable(uint256))
RULING_WIN: public(immutable(uint256))

leases: public(HashMap[uint256, Lease])
count: public(uint256)
credit: public(HashMap[address, uint256])
locked: public(uint256)


@deploy
def __init__(claim_win: uint256, reply_win: uint256, ruling_win: uint256):
    assert claim_win > 0 and reply_win > 0 and ruling_win > 0, "windows must be positive"
    CLAIM_WIN = claim_win
    REPLY_WIN = reply_win
    RULING_WIN = ruling_win


@external
def create(tenant: address, arbiter: address, amount: uint256, ends: uint256) -> uint256:
    assert tenant != empty(address) and tenant != msg.sender, "bad tenant"
    assert arbiter != empty(address), "bad arbiter"
    assert arbiter != msg.sender and arbiter != tenant, "arbiter must be independent"
    assert amount > 0, "zero amount"
    assert ends > block.timestamp, "ends in the past"
    lid: uint256 = self.count
    self.count = lid + 1
    self.leases[lid] = Lease(
        landlord=msg.sender,
        tenant=tenant,
        arbiter=arbiter,
        amount=amount,
        ends=ends,
        deduct=0,
        stamp=0,
        reason=empty(bytes32),
        state=CREATED,
    )
    log Created(id=lid, landlord=msg.sender, tenant=tenant, arbiter=arbiter, amount=amount, ends=ends)
    return lid


@external
@payable
def fund(lid: uint256):
    lse: Lease = self.leases[lid]
    assert lse.state == CREATED, "not open for funding"
    assert msg.sender == lse.tenant, "only tenant"
    assert msg.value == lse.amount, "wrong amount"
    assert block.timestamp < lse.ends, "lease already ended"
    self.leases[lid].state = ACTIVE
    self.locked += msg.value
    log Funded(id=lid, amount=msg.value)


@external
def cancel(lid: uint256):
    lse: Lease = self.leases[lid]
    assert lse.state == CREATED, "cannot cancel"
    assert msg.sender == lse.landlord, "only landlord"
    self.leases[lid].state = CANCELLED
    log Cancelled(id=lid)


@external
def release(lid: uint256):
    lse: Lease = self.leases[lid]
    assert lse.state == ACTIVE, "not active"
    assert msg.sender == lse.landlord, "only landlord"
    self._settle(lid, 0, 1)


@external
def claim(lid: uint256, deduct: uint256, reason: bytes32):
    lse: Lease = self.leases[lid]
    assert lse.state == ACTIVE, "not active"
    assert msg.sender == lse.landlord, "only landlord"
    assert block.timestamp >= lse.ends, "lease not over"
    assert block.timestamp < lse.ends + CLAIM_WIN, "claim window closed"
    assert deduct <= lse.amount, "deduction exceeds deposit"
    if deduct == 0:
        self._settle(lid, 0, 1)
        return
    self.leases[lid].deduct = deduct
    self.leases[lid].reason = reason
    self.leases[lid].stamp = block.timestamp
    self.leases[lid].state = CLAIMED
    log Claimed(id=lid, deduct=deduct, reason=reason)


@external
def accept(lid: uint256):
    lse: Lease = self.leases[lid]
    assert lse.state == CLAIMED, "nothing to accept"
    assert msg.sender == lse.tenant, "only tenant"
    self._settle(lid, lse.deduct, 2)


@external
def dispute(lid: uint256):
    lse: Lease = self.leases[lid]
    assert lse.state == CLAIMED, "nothing to dispute"
    assert msg.sender == lse.tenant, "only tenant"
    assert block.timestamp < lse.stamp + REPLY_WIN, "reply window closed"
    self.leases[lid].state = DISPUTED
    self.leases[lid].stamp = block.timestamp
    log Disputed(id=lid)


@external
def resolve(lid: uint256, to_landlord: uint256):
    lse: Lease = self.leases[lid]
    assert lse.state == DISPUTED, "not disputed"
    assert msg.sender == lse.arbiter, "only arbiter"
    assert block.timestamp < lse.stamp + RULING_WIN, "ruling window closed"
    assert to_landlord <= lse.deduct, "award exceeds claim"
    self._settle(lid, to_landlord, 3)


@external
def finalize(lid: uint256):
    lse: Lease = self.leases[lid]
    if lse.state == ACTIVE:
        assert block.timestamp >= lse.ends + CLAIM_WIN, "claim window open"
        self._settle(lid, 0, 4)
    elif lse.state == CLAIMED:
        assert block.timestamp >= lse.stamp + REPLY_WIN, "reply window open"
        self._settle(lid, lse.deduct, 5)
    elif lse.state == DISPUTED:
        assert block.timestamp >= lse.stamp + RULING_WIN, "ruling window open"
        self._settle(lid, lse.deduct // 2, 6)
    else:
        raise "nothing to finalize"


@external
@nonreentrant
def withdraw():
    amt: uint256 = self.credit[msg.sender]
    assert amt > 0, "nothing to withdraw"
    self.credit[msg.sender] = 0
    raw_call(msg.sender, b"", value=amt)
    log Withdrawn(who=msg.sender, amount=amt)


@internal
def _settle(lid: uint256, to_landlord: uint256, how: uint8):
    lse: Lease = self.leases[lid]
    rest: uint256 = lse.amount - to_landlord
    self.leases[lid].state = SETTLED
    self.locked -= lse.amount
    self.credit[lse.landlord] += to_landlord
    self.credit[lse.tenant] += rest
    log Settled(id=lid, to_landlord=to_landlord, to_tenant=rest, how=how)
