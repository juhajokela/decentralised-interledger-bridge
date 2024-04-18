# Running tests

Testing framework: `pytest`

Include pytest option `-s` to output the test prints; `-v` to list all the test methods.
To run following tests, `pytest` and `pytest-asyncio` need be installed.

    pip install pytest pytest-asyncio

## Unit tests

The current modules have a lot of dependencies, so unit tests are very small, mainly concerning initializations.

    pytest tests/unit/
    pytest tests/unit/test_interledger.py

## System tests

This test set is not self-dependent. The modules interacting with ethereum need a local ethereum instance running. These examples use ganache-cli.

**Testing Ethereum Initiator and Responder: One instance running on port 7545**

    ganache-cli -p 7545
    pytest tests/system/test_ethereuminitiator.py
    pytest tests/system/test_ethereumresponder.py

These tests examine the correctness of different modules of EthereumInitiator and EthereumResponder classes.

**Testing Interledger: Two instances running on ports 7545 and 7546**

    ganache-cli -p 7545
    ganache-cli -p 7546
    make migrate-both
    python3 start_dib.py configs/dib-node-1-1.cfg node.node_count=2
    python3 start_dib.py configs/dib-node-1-2.cfg node.node_count=2
    python3 -m pytest -s tests/system/ethereum_multiple.py --config_file=configs/dib-node-1-1.cfg --transfers=10

This test examine both way communication between two different ledgers which is controlled by the interledger component.

## Performance measurements

To evaluate the cost and performance in throughput, the following measurements can be carried out.

First set up the test networks respectively, setting a block time with the `-b` flag.

    ganache-cli -p 7545 -b 1
    ganache-cli -p 7546 -b 1

The next step is to deploy the sample `GameToken` smart contract on the test networks above, respectively.

    make migrate-both

This way, the measurement of total gas usage and elapsed time of complete processes of the sample GameToken transfer with and without the Interledger component can be extracted by running the following tests.

    python3 -m pytest -s tests/system/ethereum_multiple.py --config_file=configs/dib-node-1-1.cfg --transfers=1000

Note that the comparison measurement without using the component is conducted by the following. In this case, the `GameTokenWithoutInterledger` smart contract should be used on ledgers of both sides.

    cd ledgers/solidity
    truffle migrate --reset --f 7 --network left
    truffle migrate --reset --f 7 --network right

Above steps are to be taken to deploy that smart contract for comparision purposes.

Similarly, the performance when processing simultaneous incoming transfers can be tested and analyzed by running the following two tests respectively, after the same set up above.

    pytest tests/system/ethereum_with_interledger_multiple.py
    pytest tests/system/ethereum_without_interledger_multiple.py

Note the first one above is for simultaneous `GameToken` smart contract transfers with interledger, while the second one is for the comparison without the component, where `GameTokenWithoutInterledger` smart contract should be deployed and used.
