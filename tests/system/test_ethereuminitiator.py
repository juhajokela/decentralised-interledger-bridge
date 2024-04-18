from interledger.adapter.interfaces import ErrorCode
from interledger.adapter.ethereum import EthereumInitiator
from .test_setup import setUp, setup_provider, create_token, accept_token, transfer_token
import pytest, asyncio
import os, json
import web3
from web3 import Web3
from uuid import uuid4

# # # Global view
# #
# #  Ledger <- Initiator <- Interledeger -> Responder -> Ledger
#

###################################

# # # Local view
# #
# #  Ledger <- EthereumInitiator
#
# #
#

def test_init(config_file):

    # Setup web3 and state
    cfg = setUp(config_file, 'left')

    init = EthereumInitiator(cfg)

    w3 = setup_provider(cfg.url, cfg.port, cfg.poa, cfg.ipc_path)
    token_instance = w3.eth.contract(abi=cfg.contract_abi, address=cfg.contract_address)

    assert init.web3.isConnected()
    assert init.minter == cfg.minter
    #assert init.contract == token_instance
    assert init.timeout == 120

#
# Test get_transfers
#
@pytest.mark.asyncio
async def test_initiator_listen_for_events(config_file):

    # Setup the state
    cfg = setUp(config_file, 'left')
    w3 = setup_provider(cfg.url, cfg.port, cfg.poa, cfg.ipc_path)
    token_instance = w3.eth.contract(abi=cfg.contract_abi, address=cfg.contract_address)
    contract_minter = w3.eth.accounts[0]
    bob = w3.eth.accounts[1]

    # Create a token
    ids = [uuid4().int, uuid4().int, uuid4().int, uuid4().int]
    tokenURI = "weapons/"
    assetName = w3.toBytes(text="Vorpal Sword")

    for tokenId in ids:
        tx_hash = token_instance.functions.mint(bob, tokenId, tokenURI, assetName).transact({'from': contract_minter})
        w3.eth.waitForTransactionReceipt(tx_hash)
        assert token_instance.functions.getStateOfToken(tokenId).call() == 0

        # Change to valid state
        await accept_token(contract_minter, token_instance, w3, tokenId)
        assert token_instance.functions.getStateOfToken(tokenId).call() == 2


    ### Test Ethereum Initiator ###
    init = EthereumInitiator(cfg)


    # Emit 1 event and call get_transfers
    asyncio.sleep(1)
    (data, blockNumber, cost) = await transfer_token(contract_minter, token_instance, w3, ids[0])
    assert token_instance.functions.getStateOfToken(ids[0]).call() == 1
    transfers = await init.listen_for_events()

    t = transfers[0]
    assert len(transfers) == 1
    assert t.payload['id'] == str(ids[0])
    assert t.payload['data'] == data
    assert init.last_block >= blockNumber

    # Emit 2 events and call get_transfers
    (data1, blockNumber1, cost) = await transfer_token(contract_minter, token_instance, w3, ids[1])
    assert token_instance.functions.getStateOfToken(ids[1]).call() == 1
    (data2, blockNumber2, cost) = await transfer_token(contract_minter, token_instance, w3, ids[2])

    assert token_instance.functions.getStateOfToken(ids[2]).call() == 1
    transfers = await init.listen_for_events()

    t = transfers[0]
    assert len(transfers) == 2
    assert t.payload['id'] == str(ids[1])
    assert t.payload['data'] == data1
    assert init.last_block >= blockNumber1

    t = transfers[1]
    assert t.payload['id'] == str(ids[2])
    assert t.payload['data'] == data2
    assert init.last_block >= blockNumber2



    # Emit 1 event and call get_transfers
    (data3, blockNumber3, cost) = await transfer_token(contract_minter, token_instance, w3, ids[3])
    assert token_instance.functions.getStateOfToken(ids[3]).call() == 1
    transfers = await init.listen_for_events()

    t = transfers[0]
    assert len(transfers) == 1
    assert t.payload['id'] == str(ids[3])
    assert t.payload['data'] == data3
    assert init.last_block >= blockNumber3

#
# Test abort_transfer
#
@pytest.mark.asyncio
async def test_initiator_abort(config_file):

    cfg = setUp(config_file, 'left')
    w3 = setup_provider(cfg.url, cfg.port, cfg.poa, cfg.ipc_path)

    token_instance = w3.eth.contract(abi=cfg.contract_abi, address=cfg.contract_address)
    (tokenId, cost) = await create_token(cfg.minter, token_instance, w3)
    assert token_instance.functions.getStateOfToken(tokenId).call() == 0
    await accept_token(cfg.minter, token_instance, w3, tokenId)
    assert token_instance.functions.getStateOfToken(tokenId).call() == 2
    await transfer_token(cfg.minter, token_instance, w3, tokenId)
    assert token_instance.functions.getStateOfToken(tokenId).call() == 1

    ### Test Ethereum Initiator ###
    init = EthereumInitiator(cfg)

    reason = 2
    result = await init.abort_sending(str(tokenId), reason)

    assert result["abort_status"] == True
    assert token_instance.functions.getStateOfToken(tokenId).call() == 2

    tx_hash = result["abort_tx_hash"]
    tx_info = w3.eth.getTransaction(tx_hash)
    tx_receipt = w3.eth.getTransactionReceipt(tx_hash)
    # check also other information about the transaction
    assert tx_info ['hash'] == tx_hash
    assert tx_info ['blockHash'] != None
    assert tx_info ['to'] == cfg.contract_address
    #print(tx_info)
    # check function name and abi
    decoded_input = token_instance.decode_function_input(tx_info['input'])
    #print(decoded_input)
    assert decoded_input[0].fn_name == token_instance.get_function_by_name("interledgerAbort").fn_name
    assert decoded_input[0].abi == token_instance.get_function_by_name("interledgerAbort").abi
    # check function parameters
    assert decoded_input[1]['id'] == tokenId
    assert decoded_input[1]['reason'] == 2 # ErrorCode.TRANSACTION_FAILURE


@pytest.mark.asyncio
async def test_initiator_abort_transaction_failure(config_file):

    cfg = setUp(config_file, 'left')
    w3 = setup_provider(cfg.url, cfg.port, cfg.poa, cfg.ipc_path)

    token_instance = w3.eth.contract(abi=cfg.contract_abi, address=cfg.contract_address)
    (tokenId,cost) = await create_token(cfg.minter, token_instance, w3)
    assert token_instance.functions.getStateOfToken(tokenId).call() == 0
    await accept_token(cfg.minter, token_instance, w3, tokenId)
    assert token_instance.functions.getStateOfToken(tokenId).call() == 2

    ### Test Ethereum Initiator ###
    init = EthereumInitiator(cfg)

    reason = 2
    result = await init.abort_sending(str(tokenId), reason)

    assert result["abort_status"] == False
    assert result["abort_error_code"] == ErrorCode.TRANSACTION_FAILURE
    assert result["abort_message"].find('revert') >= 0
    tx_hash = result["abort_tx_hash"]
    assert tx_hash == None
    assert token_instance.functions.getStateOfToken(tokenId).call() == 2

#
# Test commit_transfer
#
@pytest.mark.asyncio
async def test_initiator_commit(config_file):

    cfg = setUp(config_file, 'left')
    w3 = setup_provider(cfg.url, cfg.port, cfg.poa, cfg.ipc_path)

    token_instance = w3.eth.contract(abi=cfg.contract_abi, address=cfg.contract_address)
    (tokenId,cost) = await create_token(cfg.minter, token_instance, w3)
    assert token_instance.functions.getStateOfToken(tokenId).call() == 0
    await accept_token(cfg.minter, token_instance, w3, tokenId)
    assert token_instance.functions.getStateOfToken(tokenId).call() == 2
    await transfer_token(cfg.minter, token_instance, w3, tokenId)
    assert token_instance.functions.getStateOfToken(tokenId).call() == 1

    ### Test Ethereum Initiator ###
    init = EthereumInitiator(cfg)

    result = await init.commit_sending(str(tokenId))

    assert result["commit_status"] == True
    assert token_instance.functions.getStateOfToken(tokenId).call() == 0

    tx_hash = result["commit_tx_hash"]
    tx_info = w3.eth.getTransaction(tx_hash)
    tx_receipt = w3.eth.getTransactionReceipt(tx_hash)
    # check also other information about the transaction
    assert tx_info ['hash'] == tx_hash
    assert tx_info ['blockHash'] != None
    assert tx_info ['to'] == cfg.contract_address
    print(tx_info)
    # check function name and abi
    decoded_input = token_instance.decode_function_input(tx_info['input'])
    assert decoded_input[0].fn_name == token_instance.get_function_by_signature('interledgerCommit(uint256)').fn_name
    assert decoded_input[0].abi == token_instance.get_function_by_signature('interledgerCommit(uint256)').abi
    # check function parameters
    assert decoded_input[1]['id'] == tokenId

@pytest.mark.asyncio
async def test_initiator_commit_transaction_failure(config_file):

    cfg = setUp(config_file, 'left')
    w3 = setup_provider(cfg.url, cfg.port, cfg.poa, cfg.ipc_path)

    token_instance = w3.eth.contract(abi=cfg.contract_abi, address=cfg.contract_address)
    (tokenId,cost) = await create_token(cfg.minter, token_instance, w3)
    assert token_instance.functions.getStateOfToken(tokenId).call() == 0
    await accept_token(cfg.minter, token_instance, w3, tokenId)
    assert token_instance.functions.getStateOfToken(tokenId).call() == 2

    ### Test Ethereum Initiator ###
    init = EthereumInitiator(cfg)

    result = await init.commit_sending(str(tokenId))

    assert result["commit_status"] == False
    assert result["commit_error_code"] == ErrorCode.TRANSACTION_FAILURE
    assert result["commit_message"].find('revert') >= 0
    tx_hash = result["commit_tx_hash"]
    assert tx_hash == None

    assert token_instance.functions.getStateOfToken(tokenId).call() == 2
