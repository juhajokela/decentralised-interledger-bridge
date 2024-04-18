import asyncio
import os
import pytest
import time

from .test_setup import setUp, setup_provider, non_blocking_accept_token, non_blocking_transfer_token, non_blocking_create_token
from .utils import json_write

SCRIPT_DIR_PATH = os.path.dirname(os.path.abspath(__file__))

# # # Global view
#
#  LedgerA <- Initiator <- Interledeger -> Responder -> LedgerB
# in this test no Interledger node is started, it should be started separately

@pytest.mark.asyncio
async def test_interledger_with_two_ethereum_multiple_transfer(config_files, transfers):
    print(config_files, transfers)

    results = {}
    for config_file in config_files:

        # set up ledgerA and ledgerB
        cfg_A = setUp(config_file, 'left')
        cfg_B = setUp(config_file, 'right')

        w3_A = setup_provider(cfg_A.url, cfg_A.port, cfg_A.poa, cfg_A.ipc_path)
        w3_B = setup_provider(cfg_B.url, cfg_B.port, cfg_B.poa, cfg_B.ipc_path)

        token_instance_A = w3_A.eth.contract(abi=cfg_A.contract_abi, address=cfg_A.contract_address)
        token_instance_B = w3_B.eth.contract(abi=cfg_B.contract_abi, address=cfg_B.contract_address)

        print("Test setup ready, creating tokens for multiple asset transfers")

        # prepare for asset transfer
        tokens = []

        # needed for token creation
        create = []

        # these contain tokens transiting between various states
        transfer_out = []
        need_accept = []
        accept = []
        completed = []

        # Create tokens in both ledgers and set their state in ledger A
        start_time = time.time()

        filter_A = token_instance_A.events.NewTokenAsset().createFilter(fromBlock = 'latest')
        filter_A.get_all_entries()

        for i in range(transfers):
            (tokenId, tx_hash) = non_blocking_create_token(cfg_A.minter, token_instance_A, w3_A)
            (tokenId, tx_hash) = non_blocking_create_token(cfg_B.minter, token_instance_B, w3_B, tokenId)
            create.append(tokenId)
            if (i+1) % 10 == 0:
                print('transfers:', i+1, '/', transfers)

        #print("len create: ", len(create))

        while(True):
            asyncio.sleep(0.1)

            # Check wherever token has been created in both ledgers
            entries = filter_A.get_new_entries()

            to_remove = []
            for i, entry in enumerate(entries):
                token = entry['args']['tokenId']
                if token in create:
                    need_accept.append(token)
                    to_remove.append(token)
                if (i+1) % 10 == 0:
                    print('entries:', i+1, '/', len(entries))

            create = [x for x in create if x not in to_remove]

            # Accept created tokens in ledger A
            to_remove = []
            for i, token in enumerate(need_accept):
                non_blocking_accept_token(cfg_A.minter, token_instance_A, w3_A, token)
                accept.append(token)
                to_remove.append(token)
                if (i+1) % 10 == 0:
                    print('need_accept:', i+1, '/', len(need_accept))

            need_accept = [x for x in need_accept if x not in to_remove]

            # Check wherever token is in Here state in ledger A
            to_remove = []
            for i, token in enumerate(accept):
                if token_instance_A.functions.getStateOfToken(token).call() == 2:
                    tokens.append(token)
                    to_remove.append(token)
                if (i+1) % 10 == 0:
                    print('accept:', i+1, '/', len(accept))

            accept = [x for x in accept if x not in to_remove]

            print(f"Len tokens {len(tokens)}, len need accept {len(need_accept)}, len accept {len(accept)}")

            if (len(tokens) == transfers) and (len(need_accept) == 0) and (len(accept) == 0):
                # all tokens have been created and accepted in ledger A
                break

        elapsed_time = time.time() - start_time
        print(f"Token setup ready for {transfers} simultaneous transfers, took: {elapsed_time} seconds")

        results[config_file] = tokens

    asyncio.sleep(2) # make sure all tokens are created properly

    file_path = os.path.join(SCRIPT_DIR_PATH, 'temp.json')
    print('temp filepath:', file_path)
    json_write(file_path, results, indent=2)
