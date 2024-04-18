#!/bin/sh
# Used inside Docker Compose environment
# deploys smart contracts and runs Interledger afterwards


# TODO: wait until both Ganache instances are running
# ....

# deploy client smart contracts, this will update configuration file
cd ledgers/solidity/
npx truffle migrate --reset --f 6 --to 6 --network left_compose --nodes 3 --config_file ../../configs/dib-compose.cfg
npx truffle migrate --reset --f 6 --to 6 --network right_compose --nodes 3 --config_file ../../configs/dib-compose.cfg
cd ../..

# copy the updated configuration files to shared directory
cp configs/dib-compose-node-1.cfg configs/dib-compose-node-2.cfg configs/dib-compose-node-3.cfg config/
