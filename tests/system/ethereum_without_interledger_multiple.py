from .test_setup import setUp, setup_provider, create_token, accept_token, transfer_token, commit_transaction, abort_transaction, calculate_used_gas, non_blocking_accept_token, non_blocking_create_token, non_blocking_transfer_token, non_blocking_commit_transaction, non_blocking_abort_transaction
from web3 import Web3
from unittest.mock import patch
import pytest, time, json, os
import asyncio
import time

@pytest.mark.asyncio
async def test_with_two_ethereum_multiple_transfer_without_interledger(config_file):

    # set up ledgerA and ledgerB
    cfg_A = setUp(config_file, 'left')
    cfg_B = setUp(config_file, 'right')

    w3_A = setup_provider(cfg_A.url, cfg_A.port, cfg_A.poa, cfg_A.ipc_path)
    w3_B = setup_provider(cfg_B.url, cfg_B.port, cfg_B.poa, cfg_B.ipc_path)

    token_instance_A = w3_A.eth.contract(abi=cfg_A.contract_abi, address=cfg_A.contract_address)
    token_instance_B = w3_B.eth.contract(abi=cfg_B.contract_abi, address=cfg_B.contract_address)

    print("Test setup ready, performing measurement for multiple asset transfers")

    # prepare for asset transfer
    #simultaneous_transfers = [1, 2, 5, 10, 20, 50]
    simultaneous_transfers = [100]
    for transfers in simultaneous_transfers:
        tokens = []

        # needed for token creation
        create = []

        # these contain tokens transiting between various states
        accept = []
        need_accept = []
        need_commit = []
        completed = []

        # Create tokens in both ledgers and set their state in ledger A
        start_time = time.time()

        filter_A = token_instance_A.events.NewTokenAsset().createFilter(fromBlock = 'latest')
        filter_B = token_instance_B.events.NewTokenAsset().createFilter(fromBlock = 'latest')

        for i in range(transfers):
            (tokenId, tx_hash) = non_blocking_create_token(cfg_A.minter, token_instance_A, w3_A)
            (tokenId, tx_hash) = non_blocking_create_token(cfg_B.minter, token_instance_B, w3_B, tokenId)
            create.append(tokenId)

        while(True):
            # Check wherever token has been created in both ledgers
            to_remove = []
            entries = filter_A.get_new_entries()

            for entry in entries:
                token = entry['args']['tokenId']
                if token in create:
                    need_accept.append(token)
                    to_remove.append(token)

            create = [x for x in create if x not in to_remove]

            # Accept created tokens in ledger A
            to_remove = []
            for token in need_accept:
                non_blocking_accept_token(cfg_A.minter, token_instance_A, w3_A, token)
                accept.append(token)
                to_remove.append(token)

            need_accept = [x for x in need_accept if x not in to_remove]

            # Check wherever token is in Here state in ledger A
            to_remove = []
            for token in accept:
                if token_instance_A.functions.getStateOfToken(tokenId).call() == 2:
                    tokens.append(token)
                    to_remove.append(token)

            accept = [x for x in accept if x not in to_remove]

            if (len(tokens) == transfers) and (len(need_accept) == 0) and (len(accept) == 0):
                # all tokens have been created and accepted in ledger A
                break

        elapsed_time = time.time() - start_time
        print(f"Token setup ready for {transfers} simultaneous transfers, took: {elapsed_time} seconds")

        # Create filters to check InterledgerEventSending/Here/NotHere events
        sending_filter = token_instance_A.events.InterledgerEventSending().createFilter(fromBlock = 'latest')
        sending_filter.get_all_entries()
        commit_filter = token_instance_A.events.NotHere().createFilter(fromBlock = 'latest')
        commit_filter.get_all_entries()
        receive_filter = token_instance_B.events.Here().createFilter(fromBlock = 'latest')
        receive_filter.get_all_entries()

        # Initiate transfer by calling transferOut for each token
        start_time = time.time()
        for token in tokens:
            tx_hash1 = non_blocking_transfer_token(cfg_A.minter, token_instance_A, w3_A, token)

        while(True):
            # Check wherever some tokens have moved to TransferOut state
            to_remove = []

            sending_entries = sending_filter.get_new_entries()
            for entry in sending_entries:
                token = entry['args']['id']
                need_accept.append(token)

            # Process tokens for which accept should be called in ledger B
            to_remove = []
            for token in need_accept:
                tx_hash2 = non_blocking_accept_token(cfg_B.minter, token_instance_B, w3_B, token)
                to_remove.append(token)

            need_accept = [x for x in need_accept if x not in to_remove]


            # Process accepted tokens, these can be committed to ledger A
            receive_entries = receive_filter.get_new_entries()
            for entry in receive_entries:
                token = entry['args']['id']
                need_commit.append(token)


            # Process tokens for which commit should be called in ledger A
            to_remove = []
            for token in need_commit:
                tx_hash3 = non_blocking_commit_transaction(cfg_A.minter, token_instance_A, w3_A, token)
                to_remove.append(token)

            need_commit = [x for x in need_commit if x not in to_remove]


            # Check wherever transfer has been completed (token is in NotHere state in ledger A)
            commit_entries = commit_filter.get_new_entries()
            for entry in commit_entries:
                token = entry['args']['id']
                completed.append(token)

            # Check wherever we have completed all transfers
            if len(completed) == transfers:
                elapsed_time = time.time() - start_time
                print(f"Took {elapsed_time} seconds for completing {transfers} transfers, TPS: {transfers/elapsed_time}\n")
                break

            await asyncio.sleep(0.01)
