from interledger.adapter.interfaces import Initiator, Responder
from interledger.interledger import DecentralizedInterledger
from interledger.configs import NodeConfig


#import sys, os
#sys.path.append(os.path.realpath('./src'))
def test_interledger_init():
    # Test initialization of interledger

    init = Initiator()
    resp = Responder()
    config = NodeConfig(0, 1, 'secret', 10, 2, True, True, True, False)

    interledger = DecentralizedInterledger(init, resp, config)

    assert interledger.initiator == init
    assert interledger.responder == resp
    assert interledger.config == config
    assert interledger.running == False
