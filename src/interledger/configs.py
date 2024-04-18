import json
import sys

from dataclasses import dataclass

from web3 import Web3


@dataclass
class NodeConfig:
    node_count: int
    node_id: int
    secret: str
    timeout_initial: int
    timeout_backoff: int
    timeout_enabled: bool

    confirm_transfer: bool
    verification_enabled: bool
    route_to_first_node: bool


# Class for storing all Ethereum-related configuration options
class EthereumConfig(object):

    def __init__(self):
        # minter of the contract who is in charge of data emiting and committing
        # the status of the data transfer
        self.minter = None

        # address of data transfer contract implementing the Interledger interface
        self.contract_address = None

        # contract ABI
        self.contract_abi = None

        # url and port for connecting to the ledger
        self.url = None
        self.port = None

        # IPC path for IPCProviders (overrides port/url)
        self.ipc_path = None

        # private key/password to unlock the account if used
        self.private_key = None
        self.password = None

        # whether to inject the PoA middleware for the ledger connection
        self.poa = None


def parse_node_config(parser, args_config={}):
    section = 'node'
    cfg = parser[section]
    return NodeConfig(
        node_id = int(args_config.get('node_id') or parser.get(section, 'node_id')),  # 0
        node_count = int(args_config.get('node_count') or parser.get(section, 'node_count')),  # 1
        secret = parser.get(section, 'secret'),

        # timeout
        timeout_initial = cfg.getint('timeout_initial', fallback=30),
        timeout_backoff = cfg.getint('timeout_backoff', fallback=2),
        timeout_enabled = not cfg.getboolean('timeout_disabled', fallback=False),

        # for testing
        confirm_transfer = cfg.getboolean('confirm_transfer', fallback=True),
        verification_enabled = not cfg.getboolean('verification_disabled', fallback=False),
        route_to_first_node = cfg.getboolean('route_to_first_node', fallback=False)
    )


# Helper function to read Ethereum related options from configuration file
def parse_ethereum(parser, section):
    net_type = parser.get(section, 'type')
    assert net_type == 'ethereum'

    cfg = EthereumConfig()

    cfg.url = parser.get(section, 'url')
    try:
        cfg.port = parser.get(section, 'port')
    except:
        pass
    #path = url
    #if port:
    #    path += ':' + str(port)
    cfg.minter = Web3.toChecksumAddress(parser.get(section, 'minter'))
    cfg.contract_address = Web3.toChecksumAddress(parser.get(section, 'contract'))
    abi_file = parser.get(section, 'contract_abi')

    #contract_abi = ''
    try:
        with open(abi_file) as json_file:
            cfg.contract_abi = json.load(json_file)
    except:
        print("ERROR parsing smart contract ABI file for:", section , ". Error:", sys.exc_info()[0])
        exit(-1)

    try:
        cfg.private_key = parser.get(section, 'private_key')
    except:
        pass

    try:
        cfg.password = parser.get(section, 'password')
    except:
        pass

    try:
        cfg.poa = parser.get(section, 'poa') in ('true', 'True')
    except:
        pass

    try:
        cfg.ipc_path = parser.get(section, 'ipc_path')
    except:
        pass

    return cfg


# Helper function to read KSI related options from configuration file
def parse_ksi(parser, section):
    net_type = parser.get(section, 'type')
    assert net_type == 'ksi'

    # Read data
    url = parser.get(section, 'url')
    hash_algorithm = parser.get(section, 'hash_algorithm')
    username = parser.get(section, 'username')
    password = parser.get(section, 'password')

    return (url, hash_algorithm, username, password)


# Helper function to read Hyperledger Indy related options from configuration file
def parse_indy(parser, section):
    net_type = parser.get(section, 'type')
    assert net_type == 'indy'

    # Read data
    target_did = parser.get(section, 'target_did')
    pool_name = parser.get(section, 'pool_name')
    protocol_version = int(parser.get(section, 'protocol_version'))
    genesis_file_path = parser.get(section, 'genesis_file_path')
    wallet_id = parser.get(section, 'wallet_id')
    wallet_key = parser.get(section, 'wallet_key')

    return (target_did, pool_name, protocol_version, genesis_file_path, wallet_id, wallet_key)


# Helper function to read HyperLedger Fabric related options from configuration file
def parse_fabric(parser, section):
    net_type = parser.get(section, 'type')
    assert net_type == 'fabric'

    # Read data
    net_profile = parser.get(section, 'network_profile')
    channel_name = parser.get(section, 'channel_name')
    cc_name = parser.get(section, 'cc_name')
    cc_version = parser.get(section, 'cc_version')
    org_name = parser.get(section, 'org_name')
    user_name = parser.get(section, 'user_name')
    peer_name = parser.get(section, 'peer_name')

    return (net_profile, channel_name, cc_name, cc_version, org_name, user_name, peer_name)
