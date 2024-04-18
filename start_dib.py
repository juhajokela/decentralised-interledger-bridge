import sys, asyncio
from collections import defaultdict

from web3 import Web3
from configparser import ConfigParser

from src.interledger.adapter.ksi import KSIResponder  # TODO: replace by patched version
from src.interledger.adapter.ethereum import EthereumInitiator, EthereumResponder
from src.interledger.adapter.fabric import FabricInitiator, FabricResponder
from src.interledger.configs import (
    parse_ethereum,
    parse_ksi,
    parse_fabric,
    parse_node_config,
)
from src.interledger.interledger import DecentralizedInterledger


def parse_args_config(args):
    # node.node_id=0 -> {'node': 'node_id': '0'}
    config = defaultdict(dict)
    for arg in args:
        section, setting = arg.split('.')
        key, value = setting.split('=')
        config[section][key] = value
    return config


# Builder a left to right DIB instance
# Note: KSI is only supported as destination ledger
def left_to_right_bridge(parser, left, right):
    initiator = None
    responder = None
    ledger_left = parser.get(left, 'type')
    ledger_right = parser.get(right, 'type')

    # Left ledger with initiator
    if ledger_left == "ethereum":
        cfg = parse_ethereum(parser, left)
        # Create Initiator
        initiator = EthereumInitiator(cfg)
    elif ledger_left == "fabric":
        (net_profile, channel_name, cc_name, cc_version, org_name, user_name, peer_name) = parse_fabric(parser, left)
        # Create Initiator
        initiator = FabricInitiator(net_profile, channel_name, cc_name, cc_version, org_name, user_name, peer_name)
    else:
        print(f"ERROR: ledger type {ledger_left} not supported yet")
        exit(1)

    # Right ledger with responder
    if ledger_right == "ethereum":
        cfg = parse_ethereum(parser, right)
        # Create Responder
        responder = EthereumResponder(cfg)
    elif ledger_right == "ksi":
        (url, hash_algorithm, username, password) = parse_ksi(parser, right)
        # Create Responder
        responder = KSIResponder(url, hash_algorithm, username, password)
    elif ledger_right == "fabric":
        (net_profile, channel_name, cc_name, cc_version, org_name, user_name, peer_name) = parse_fabric(parser, left)
        # Create Responder
        responder = FabricResponder(net_profile, channel_name, cc_name, cc_version, org_name, user_name, peer_name)
    else:
        print(f"ERROR: ledger type {ledger_right} not supported yet")
        exit(1)

    return (initiator, responder)


# Builder a right to left DIB instance
# Note: KSI is only supported as destination ledger
def right_to_left_bridge(parser, left, right):
    initiator = None
    responder = None
    ledger_left = parser.get(left, 'type')
    ledger_right = parser.get(right, 'type')

    # Right ledger with initiator
    if ledger_right == "ethereum":
        #(minter, contract_address, contract_abi, url, port, private_key, password, poa, ipc_path) = parse_ethereum(parser, right)
        cfg = parse_ethereum(parser, right)
        # Create Initiator
        initiator = EthereumInitiator(cfg)
    elif ledger_right == "fabric":
        (net_profile, channel_name, cc_name, cc_version, org_name, user_name, peer_name) = parse_fabric(parser, left)
        # Create Initiator
        initiator = FabricInitiator(net_profile, channel_name, cc_name, cc_version, org_name, user_name, peer_name)
    else :
        print(f"ERROR: ledger type {ledger_right} not supported yet")
        exit(1)

    # Left ledger with Responder
    if ledger_left == "ethereum":
        cfg = parse_ethereum(parser, left)
        # Create Responder
        responder = EthereumResponder(cfg)
    elif ledger_left == "ksi":
        (url, hash_algorithm, username, password) = parse_ksi(parser, left)
        responder = KSIResponder(url, hash_algorithm, username, password)
    elif ledger_left == "fabric":
        (net_profile, channel_name, cc_name, cc_version, org_name, user_name, peer_name) = parse_fabric(parser, left)
        # Create Responder
        responder = FabricResponder(net_profile, channel_name, cc_name, cc_version, org_name, user_name, peer_name)
    else :
        print(f"ERROR: ledger type {ledger_left} not supported yet")
        exit(1)

    return (initiator, responder)


def main():
    # Parse command line input
    if len(sys.argv) <= 1:
        print("ERROR: Provide a *.cfg config file to initialize the Decentralized Interledger instance.")
        exit(1)
    parser = ConfigParser()
    parser.read(sys.argv[1])

    args_config = parse_args_config(sys.argv[2:])

    # Get direction
    direction = parser.get('service', 'direction')
    left = parser.get('service', 'left')
    right = parser.get('service', 'right')

    # Build interledger bridge(s)
    dib_left_to_right = None
    dib_right_to_left = None

    if direction == "left-to-right":
        (initiator, responder) = left_to_right_bridge(parser, left, right)
        node_cfg = parse_node_config(parser, args_config['node'])
        dib_left_to_right = DecentralizedInterledger(initiator, responder, node_cfg)
    elif direction == "right-to-left":
        (initiator, responder) = right_to_left_bridge(parser, left, right)
        node_cfg = parse_node_config(parser, args_config['node'])
        dib_right_to_left = DecentralizedInterledger(initiator, responder, node_cfg)
    elif direction == "both": # dsm2 is ledger in other direction
        (initiator_lr, responder_lr) = left_to_right_bridge(parser, left, right)
        (initiator_rl, responder_rl) = right_to_left_bridge(parser, left, right)
        node_cfg = parse_node_config(parser, args_config['node'])
        dib_left_to_right = DecentralizedInterledger(initiator_lr, responder_lr, node_cfg)
        node_cfg = parse_node_config(parser, args_config['node'])
        dib_right_to_left = DecentralizedInterledger(initiator_rl, responder_rl, node_cfg)
    else:
        print("ERROR: supported 'direction' values are 'left-to-right', 'right-to-left' or 'both'")
        print("Check your configuration file")
        exit(1)

    task = None

    if dib_left_to_right and dib_right_to_left:
        future_left_to_right = asyncio.ensure_future(dib_left_to_right.run())
        future_right_to_left = asyncio.ensure_future(dib_right_to_left.run())
        task = asyncio.gather(future_left_to_right, future_right_to_left)
        print("Starting running routine for *double* sided interledger")
    elif dib_left_to_right:
        task = asyncio.ensure_future(dib_left_to_right.run())
        print("Starting running routine for *left to right* interledger")
    elif dib_right_to_left:
        task = asyncio.ensure_future(dib_right_to_left.run())
        print("Starting running routine for *right to left* interledger")
    else:
        print("ERROR while creating tasks for interledger")
        exit(1)

    return (task, dib_left_to_right, dib_right_to_left)

if __name__ == "__main__":
    (task, dib1, dib2) = main()
    try:
        loop = asyncio.get_event_loop()
        loop.run_until_complete(task)
    except KeyboardInterrupt as e:
        print("-- Interrupted by keyword --")
        if dib1:
            dib1.stop()
        if dib2:
            dib2.stop()
        loop.run_until_complete(task)
        loop.close()
        print("-- Finished correctly --")
