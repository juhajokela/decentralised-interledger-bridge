# Solidity
compile:
	cd ledgers/solidity && npx truffle compile

migrate:
	cd ledgers/solidity && npx truffle migrate --reset

migrate-both: migrate-left migrate-right

migrate-left:
	cd ledgers/solidity && npx truffle migrate --reset --f 6 --to 6 --network left --deployments 1 --nodes 6 --config_file ../../configs/dib.cfg

migrate-right:
	cd ledgers/solidity && npx truffle migrate --reset --f 6 --to 6 --network right --deployments 1 --nodes 6 --config_file ../../configs/dib.cfg

migrate-10-both: migrate-10-left migrate-10-right

migrate-10-left:
	cd ledgers/solidity && npx truffle migrate --reset --f 6 --to 6 --network left --deployments 10 --nodes 6 --config_file ../../configs/dib.cfg

migrate-10-right:
	cd ledgers/solidity && npx truffle migrate --reset --f 6 --to 6 --network right --deployments 10 --nodes 6 --config_file ../../configs/dib.cfg

test-contracts:
	cd ledgers/solidity && npx truffle test

# Module testing
test-interledger:
	PYTHONPATH=$$PWD/src pytest tests/test_interledger.py -s

test-ethereum-ledger:
	PYTHONPATH=$$PWD/src pytest tests/test_ethereum_ledger.py -s

test-integration:
	PYTHONPATH=$$PWD/src pytest tests/test_integration.py -s

test-db-manager:
	PYTHONPATH=$$PWD/src pytest tests/test_db_manager.py -s

test-state-initiator-responder:
	PYTHONPATH=$$PWD/src pytest tests/test_state_initiator_responder.py -s

# Documentation
html:
	cd doc && make html

latexpdf:
	cd doc && make latexpdf
