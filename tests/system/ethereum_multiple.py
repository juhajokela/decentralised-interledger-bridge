import pytest, time
import asyncio
from .test_setup import setUp, setup_provider, non_blocking_accept_token, non_blocking_transfer_token, non_blocking_create_token

# # # Global view
#
#  LedgerA <- Initiator <- Interledeger -> Responder -> LedgerB
# in this test no Interledger node is started, it should be started separately

@pytest.mark.asyncio
async def test_interledger_with_two_ethereum_multiple_transfer(config_file, transfers):

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

    count = 0
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
        to_remove = []
        entries = filter_A.get_new_entries()

        count = 0
        for i, entry in enumerate(entries):
            count = count + 1
            token = entry['args']['tokenId']
            if token in create:
                need_accept.append(token)
                to_remove.append(token)
            if (i+1) % 10 == 0:
                print('entries:', i+1, '/', len(entries))
        #print("count is: ", count)

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
    #print("\t", tokens)
    asyncio.sleep(2) # make sure all tokens are created properly

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
