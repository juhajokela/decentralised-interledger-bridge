import asyncio
import os
import pytest
import time

from .test_setup import setUp, setup_provider, non_blocking_accept_token, non_blocking_transfer_token, non_blocking_create_token
from .utils import json_read

SCRIPT_DIR_PATH = os.path.dirname(os.path.abspath(__file__))

# # # Global view
#
#  LedgerA <- Initiator <- Interledeger -> Responder -> LedgerB
# in this test no Interledger node is started, it should be started separately

@pytest.mark.asyncio
async def test_interledger_with_two_ethereum_multiple_transfer(config_file):

    # set up ledgerA and ledgerB
    cfg_A = setUp(config_file, 'left')
    cfg_B = setUp(config_file, 'right')

    w3_A = setup_provider(cfg_A.url, cfg_A.port, cfg_A.poa, cfg_A.ipc_path)
    w3_B = setup_provider(cfg_B.url, cfg_B.port, cfg_B.poa, cfg_B.ipc_path)

    token_instance_A = w3_A.eth.contract(abi=cfg_A.contract_abi, address=cfg_A.contract_address)
    token_instance_B = w3_B.eth.contract(abi=cfg_B.contract_abi, address=cfg_B.contract_address)

    print("Test setup ready, performing measurement for multiple asset transfers")

    temp = json_read(os.path.join(SCRIPT_DIR_PATH, 'temp.json'))
    tokens = temp[config_file]
    transfers = len(tokens)

    # these contain tokens transiting between various states
    transfer_out = []
    need_accept = []
    accept = []
    completed = []

    # Create filter to catch NotHere event in ledger A (Interledger transaction has been completed)
    commit_filter = token_instance_A.events.NotHere().createFilter(fromBlock = 'latest')
    commit_filter.get_all_entries()

    start_time = time.time()

    # Initiate transfer by calling transferOut for each token
    count = 0
    for token in tokens:
        tx_hash1 = non_blocking_transfer_token(cfg_A.minter, token_instance_A, w3_A, token)
        transfer_out.append(token)
        count = count + 1
        #if count == 10: # sleep for a while, otherwise will cause a problem with Ganache
        #    count = 0
        #    asyncio.sleep(0.1)

    while(True):
        commit_entries = commit_filter.get_new_entries()

        to_remove = []
        for entry in commit_entries:
            #print("Entry is: ", entry)
            token = entry['args']['id']
            completed.append(token)
            to_remove.append(token)

        transfer_out = [x for x in transfer_out if x not in to_remove]

        print(f"Len tokens {len(completed)}, transfer_out {len(transfer_out)}")

        # Check wherever we have completed all transfers
        if len(completed) == transfers:
            elapsed_time = time.time() - start_time
            print(f"Took {elapsed_time} seconds for completing {transfers} transfers, TPS: {transfers/elapsed_time}\n")
            break

        # Simulate Interledger running
        await asyncio.sleep(0.01)
