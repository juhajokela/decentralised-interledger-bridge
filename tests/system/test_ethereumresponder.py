import pytest
from web3 import Web3
from uuid import uuid4
from eth_abi import encode_abi

from interledger.adapter.interfaces import ErrorCode
from interledger.adapter.ethereum import EthereumResponder
from .test_setup import setUp, setup_provider, create_token, accept_token


# # # Local view
# #
# #  EthereumResponder -> Ledger
#
# #
#

def test_init(config_file):

    # Setup web3 and state
    cfg = setUp(config_file, 'right')
    w3 = setup_provider(cfg.url, cfg.port, cfg.poa, cfg.ipc_path)
    token_instance = w3.eth.contract(abi=cfg.contract_abi, address=cfg.contract_address)

    resp = EthereumResponder(cfg)

    resp = EthereumResponder(contract_minter, contract_address, contract_abi, url, port,
                             private_key, password, poa, ipc_path)

    assert resp.web3.isConnected()
    assert resp.minter == cfg.minter
    #assert resp.contract == token_instance
    assert resp.timeout == 120


#
# Test receive_transfer
#

@pytest.mark.asyncio
async def test_responder_receive(config_file):

    cfg = setUp(config_file, 'right')
    w3 = setup_provider(cfg.url, cfg.port, cfg.poa, cfg.ipc_path)
    token_instance = w3.eth.contract(abi=cfg.contract_abi, address=cfg.contract_address)

    # # Create a token
    (tokenId,cost) = await create_token(cfg.minter, token_instance, w3)
    assert token_instance.functions.getStateOfToken(tokenId).call() == 0
    ## Test Ethereum Responder ###

    resp = EthereumResponder(cfg)

    data = encode_abi(['uint256'], [tokenId])
    nonce = "42"
    result = await resp.send_data(nonce, data)
    #print(result)
    tx_hash = result["tx_hash"]
    tx_info = w3.eth.getTransaction(tx_hash)
    tx_receipt = w3.eth.getTransactionReceipt(tx_hash)

    assert tx_info ['blockHash'] != None
    assert tx_info ['hash'] == tx_hash
    assert tx_info ['to'] == cfg.contract_address

    # check function name and abi
    decoded_input = token_instance.decode_function_input(tx_info['input'])
    assert decoded_input[0].fn_name == token_instance.get_function_by_name("interledgerReceive").fn_name
    assert decoded_input[0].abi == token_instance.get_function_by_name("interledgerReceive").abi

    # check function parameters
    assert decoded_input[1]['data'] == data

    # check for accepted/rejected events
    logs_accept = token_instance.events.InterledgerEventAccepted().processReceipt(tx_receipt)
    logs_reject = token_instance.events.InterledgerEventRejected().processReceipt(tx_receipt)

    assert len(logs_accept) == 1
    assert logs_accept[0]['args']['nonce'] == int(nonce)
    assert len(logs_reject) == 0

    assert result["status"] == True


@pytest.mark.asyncio
async def test_responder_receive_transaction_failure(config_file):

    cfg = setUp(config_file, 'right')
    w3 = setup_provider(cfg.url, cfg.port, cfg.poa, cfg.ipc_path)
    token_instance = w3.eth.contract(abi=cfg.contract_abi, address=cfg.contract_address)

    ## Create a token
    (tokenId, cost) = await create_token(cfg.minter, token_instance, w3)
    assert token_instance.functions.getStateOfToken(tokenId).call() == 0


    ## Test Ethereum Responder ###
    resp = EthereumResponder(cfg)

    #passing wrong tokenId to simulate transaction failure
    nonce, data = "42", b"dummy"
    result = await resp.send_data(nonce, data)

    assert result["status"] == False
    assert result["tx_hash"] == None
    assert result["error_code"] == ErrorCode.TRANSACTION_FAILURE
    assert result["message"].find('revert') >= 0



@pytest.mark.asyncio
async def test_responder_receive_reject_event(config_file):

    cfg = setUp(config_file, 'right')
    w3 = setup_provider(cfg.url, cfg.port, cfg.poa, cfg.ipc_path)
    token_instance = w3.eth.contract(abi=cfg.contract_abi, address=cfg.contract_address)

    ## Create a token
    (tokenId,cost) = await create_token(cfg.minter, token_instance, w3)
    assert token_instance.functions.getStateOfToken(tokenId).call() == 0
    await accept_token(cfg.minter, token_instance, w3, tokenId)
    assert token_instance.functions.getStateOfToken(tokenId).call() == 2

    ## Test Ethereum Responder ###
    resp = EthereumResponder(cfg)

    #passing an asset with the wrong state to simulate emitting a reject event
    nonce = "42"
    data = encode_abi(['uint256'], [tokenId])
    result = await resp.send_data(nonce, data)


    tx_hash = result["tx_hash"]
    tx_info = w3.eth.getTransaction(tx_hash)
    tx_receipt = w3.eth.getTransactionReceipt(tx_hash)

    assert tx_info ['blockHash'] != None
    assert tx_info ['hash'] == tx_hash
    assert tx_info ['to'] == cfg.contract_address

    # check function name and abi
    decoded_input = token_instance.decode_function_input(tx_info['input'])
    assert decoded_input[0].fn_name == token_instance.get_function_by_name("interledgerReceive").fn_name
    assert decoded_input[0].abi == token_instance.get_function_by_name("interledgerReceive").abi


    # check for accepted/rejected events
    logs_accept = token_instance.events.InterledgerEventAccepted().processReceipt(tx_receipt)
    logs_reject = token_instance.events.InterledgerEventRejected().processReceipt(tx_receipt)

    assert len(logs_accept) == 0
    assert len(logs_reject) == 1
    assert logs_reject[0]['args']['nonce'] == int(nonce)


    assert result["status"] == False
    assert result["error_code"] == ErrorCode.APPLICATION_REJECT
    assert result["message"] == "InterledgerEventRejected() event received"
