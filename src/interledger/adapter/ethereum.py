import asyncio
import functools

from contextlib import suppress
from functools import partial
from typing import (
    Dict,
    List,
)

import web3
from web3.middleware import geth_poa_middleware

from .interfaces import Initiator, Responder, MultiResponder, ErrorCode, LedgerType
from ..configs import EthereumConfig
from ..transfer import Transfer
from ..utils import generate_hash_id, Logger


Web3 = web3.Web3


# Web3 util
class Web3Initializer:
    """This provides proper web3 wrapper for a component
    """
    def __init__(self, url: str, port=None, poa=None, ipc_path=None):

        if ipc_path:
            self.web3 = Web3(Web3.IPCProvider(ipc_path))
        else:
            protocol = url.split(":")[0].lower()
            path = url
            if port:
                path += ':' + str(port)
            if protocol in ("http", "https"):
                self.web3 = Web3(Web3.HTTPProvider(path))
            elif protocol in ("ws", "wss"):
                self.web3 = Web3(Web3.WebsocketProvider(path))
            else:
                raise ValueError("Unsupported Web3 protocol")
        if poa:
            self.web3.middleware_onion.inject(geth_poa_middleware, layer=0)

    def isUnlocked(self, account):
        try:
            self.web3.eth.sign(account, 1)
        except Exception as e:
            return False
        return True


class EthereumCommonMixin:

    async def _get_block(self, block_number: int, full_transactions=False):
        if type(block_number) != int:
            raise TypeError('value of "block_number" must be type of int')
        # Logger.log('block_number:', block_number)
        response = await asyncio.get_event_loop().run_in_executor(
            None, partial(self.web3.eth.get_block, block_number, full_transactions=full_transactions)
        )
        return response

    async def get_block(self, block_number: int, full_transactions=False):
        if not hasattr(self, 'block_cache'):
            self.block_cache = {}
        key = (block_number, full_transactions)
        if key not in self.block_cache:
            self.block_cache[key] = await self._get_block(block_number, full_transactions)
        return self.block_cache[key]

    async def find_function_call(self,
                                function_signature: str,
                                function_params: dict,
                                until: int = None) -> dict:

        function = self.contract.get_function_by_signature(function_signature)
        start_block = self.web3.eth.blockNumber
        end_block = 0

        for block_number in range(start_block, end_block-1, -1):
            block = await self.get_block(block_number, full_transactions=True)
            if until is not None and block['timestamp'] < until:
                break
            for tx in block.transactions:
                if tx.to == self.contract.address:
                    # decode the input data of the transaction
                    tx_function, tx_parameters = self.contract.decode_function_input(tx.input)
                    is_match = (
                        str(tx_function) == str(function) and
                        all(k in tx_parameters and tx_parameters[k] == v for k, v in function_params.items())
                    )
                    if is_match:
                        return {
                            'blockID': block_number,
                            'txID': tx.hash.hex(),
                            'txFunc': str(tx_function),
                            'txParams': tx_parameters,
                        }

        return {}


# Initiator implementation
class EthereumInitiator(Web3Initializer, EthereumCommonMixin, Initiator):
    """Ethereum implementation of the Initiator.
    """
    def __init__(self, cfg: EthereumConfig):
        """
        :param DIBEthereumConfig cfg: config object
        """
        Web3Initializer.__init__(self, cfg.url, cfg.port, cfg.poa, cfg.ipc_path)
        self.contract = self.web3.eth.contract(abi=cfg.contract_abi, address=cfg.contract_address)
        self.last_block = self.web3.eth.blockNumber
        self.private_key = cfg.private_key
        self.minter = cfg.minter
        self.password = cfg.password
        self.timeout = 120
        self.ledger_type = LedgerType.ETHEREUM

        # create event filter
        self.filt = self.contract.events.InterledgerEventSending().createFilter(fromBlock = 'latest')
        self.filt.get_all_entries()

        self.monitor_confirmations_cursor = self.last_block

    # Initiator functions
    async def listen_for_events(self) -> list:
        """Listen for events fired by the Initiator injected contract stored in the connected Ethereum network.

        :returns: The event transfer lists
        :rtype: list
        """
        entries = self.filt.get_new_entries()
        if len(entries) == 0:
            await asyncio.sleep(0.1)
            entries = self.filt.get_new_entries()
        return entries

    async def commit_sending(self, id: str, data: bytes = None) -> dict:
        """Initiate the commit operation to the connected ledger.

        :param str id: the identifier in the originating ledger for a data item
        :param bytes data: optional data to be passed to interledgerCommit() in smart contract

        :returns: True if the operation goes well; False otherwise
        :rtype: dict {
            'commit_status': bool,
            'commit_tx_hash': str, # transaction details
            'blockNumber': int, # transaction details
            'exception': object,# only with errors
            'commit_error_code': Enum, # only with errors
            'commit_message': str      # only with errors
        }
        """
        commit_tx_hash = None
        try:
            # unlock using private key
            if self.private_key and not self.isUnlocked(self.minter): # needs to unlock with private key
                if data: # pass data to interledgerCommit if it is available
                    transaction = self.contract.functions \
                        .interledgerCommit(Web3.toInt(text=id), data) \
                        .buildTransaction({'from': self.minter})
                else:
                    transaction = self.contract.functions \
                        .interledgerCommit(Web3.toInt(text=id)) \
                        .buildTransaction({'from': self.minter})
                transaction.update({'nonce': self.web3.eth.getTransactionCount(self.minter)})
                signed_tx = self.web3.eth.account.signTransaction(transaction, self.private_key)
                commit_tx_hash = self.web3.eth.sendRawTransaction(signed_tx.rawTransaction)
            # unlock using password
            elif self.password is not None:
                unlock = self.web3.geth.personal.unlockAccount(self.minter, self.password, 0) # unlock indefinitely
                if not unlock:
                    return {"status": False,
                            "error_code": ErrorCode.TRANSACTION_FAILURE,
                            "message": "Wrong password",
                            "commit_tx_hash": None}
                if data: # pass data to interledgerCommit if it is available
                    commit_tx_hash = self.contract.functions \
                        .interledgerCommit(Web3.toInt(text=id), data) \
                        .transact({'from': self.minter}) # type uint256 required for id in the smart contract
                else:
                    commit_tx_hash = self.contract.functions \
                        .interledgerCommit(Web3.toInt(text=id)) \
                        .transact({'from': self.minter}) # type uint256 required for id in the smart contract
                # lock the account again
                self.web3.geth.personal.lockAccount(self.minter)
            # no need to unlock
            else:
                if data: # pass data to interledgerCommit if it is available
                    commit_tx_hash = self.contract.functions \
                        .interledgerCommit(Web3.toInt(text=id), data) \
                        .transact({'from': self.minter}) # type uint256 required for id in the smart contract
                else:
                    commit_tx_hash = self.contract.functions \
                        .interledgerCommit(Web3.toInt(text=id)) \
                        .transact({'from': self.minter}) # type uint256 required for id in the smart contract
            # tx_receipt = self.web3.eth.waitForTransactionReceipt(commit_tx_hash, timeout=self.timeout)
            tx_receipt = await asyncio.get_event_loop().run_in_executor(
                None, functools.partial(self.web3.eth.waitForTransactionReceipt, commit_tx_hash, timeout=self.timeout))

            if tx_receipt['status']:
                return {"commit_status": True,
                        "commit_tx_hash": commit_tx_hash.hex(),
                        "blockNumber": tx_receipt['blockNumber']}
            else:
                # TODO search: #tx_receipt
                return {"commit_status": False,
                        "commit_error_code": ErrorCode.TRANSACTION_FAILURE,
                        "commit_message": "Error in the transaction",
                        "commit_tx_hash": commit_tx_hash.hex()}
        except web3.exceptions.TimeExhausted as e:
            # Raised by web3.eth.waitForTransactionReceipt
            return {"commit_status": False,
                    "commit_error_code": ErrorCode.TIMEOUT,
                    "commit_message": "Timeout after sending the transaction",
                    "commit_tx_hash": commit_tx_hash.hex(),
                    "exception": e}
        except ValueError as e:
            # Raised by a contract function
            return {"commit_status": False,
                    "commit_error_code": ErrorCode.TRANSACTION_FAILURE,
                    "commit_message": e.__str__(),
                    "commit_tx_hash": commit_tx_hash.hex(),
                    "exception": e}

    async def abort_sending(self, id: str, reason: int) -> dict:
        """Initiate the abort operation to the connected ledger.

        :param object transfer: the transfer to abort

        :returns: True if the operation goes well; False otherwise
        :rtype: dict {
            'abort_status': bool,
            'abort_tx_hash': str, # transaction details
            'blockNumber': int, # transaction details
            'exception': object,# only with errors
            'abort_error_code': Enum, # only with errors
            'abort_message': str      # only with errors
        }
        """
        abort_tx_hash = None
        try:
            # unlock using the private key
            if self.private_key and not self.isUnlocked(self.minter): # needs to unlock with private key
                transaction = self.contract.functions \
                    .interledgerAbort(Web3.toInt(text=id), reason) \
                    .buildTransaction({'from': self.minter})
                transaction.update({'nonce': self.web3.eth.getTransactionCount(self.minter)})
                signed_tx = self.web3.eth.account.signTransaction(transaction, self.private_key)
                abort_tx_hash = self.web3.eth.sendRawTransaction(signed_tx.rawTransaction)
            # unlock using password
            elif self.password is not None:
                unlock = self.web3.geth.personal.unlockAccount(self.minter, self.password, 0) # unlock indefinitely
                if not unlock:
                    return {"status": False,
                            "error_code": ErrorCode.TRANSACTION_FAILURE,
                            "message": "Wrong password",
                            "abort_tx_hash": None}
                abort_tx_hash = self.contract.functions \
                    .interledgerAbort(Web3.toInt(text=id), reason) \
                    .transact({'from': self.minter}) # type uint256 required for id in the smart contract
                # lock the account again
                self.web3.geth.personal.lockAccount(self.minter)
            # no need to unlock
            else:
                abort_tx_hash = self.contract.functions \
                    .interledgerAbort(Web3.toInt(text=id), reason) \
                    .transact({'from': self.minter}) # type uint256 required for id in the smart contract
            # tx_receipt = self.web3.eth.waitForTransactionReceipt(abort_tx_hash, timeout=self.timeout)
            tx_receipt = await asyncio.get_event_loop().run_in_executor(
                None, functools.partial(self.web3.eth.waitForTransactionReceipt, abort_tx_hash, timeout=self.timeout))

            if tx_receipt['status']:
                return {"abort_status": True,
                        "abort_tx_hash": abort_tx_hash.hex(),
                        "blockNumber": tx_receipt['blockNumber']}
            else:
                # TODO search: #tx_receipt
                return {"abort_status": False,
                        "abort_error_code": ErrorCode.TRANSACTION_FAILURE,
                        "abort_message": "Error in the transaction",
                        "abort_tx_hash": abort_tx_hash.hex()}
        except web3.exceptions.TimeExhausted as e:
            # Raised by web3.eth.waitForTransactionReceipt
            return {"abort_status": False,
                    "abort_error_code": ErrorCode.TIMEOUT,
                    "abort_message": "Timeout after sending the transaction",
                    "abort_tx_hash": abort_tx_hash.hex(),
                    "exception": e}
        except ValueError as e:
            # Raised by a contract function
            return {"abort_status": False,
                    "abort_error_code": ErrorCode.TRANSACTION_FAILURE,
                    "abort_message": e.__str__(),
                    "abort_tx_hash": abort_tx_hash.hex(),
                    "exception": e}

    def generate_transfer_id(self, event: dict) -> str:
        # If two events are logged in one transaction, `transactionIndex` is going to be the same.
        # Using `transactionHash` and `logIndex` should enable you to identify unique event logs.
        # The transactionIndex is the index of the transaction in the block.
        # The logIndex is the index of the log in the block logs
        seed = f"{event['blockNumber']}{event['transactionHash'].hex()}{event['logIndex']}"
        return generate_hash_id(seed, self.secret)

    async def process_event(self, event: dict) -> Transfer:
        # Helper function to create a Transfer object from a web3 event entry
        transfer_id = self.generate_transfer_id(event)
        block = await self.get_block(event['blockNumber'])
        tx_key = {
            'txID': event['transactionHash'].hex(),
            'blockID': event['blockNumber'],
        }
        transfer = Transfer(
            id=transfer_id,
            data=event['args']['data'],
            initiator_id=str(event['args']['id']),
            initiator_tx_key=tx_key,
            initiation_timestamp=block['timestamp'],
        )
        return transfer

    async def check_confirmation(self, tx: Dict[str, str]) -> str:
        tx = self.web3.eth.get_transaction(tx['txID'])
        tx_function, tx_parameters = self.contract.decode_function_input(tx["input"])

        # get the object of function that should have been called
        commit_function = self.contract.get_function_by_signature('interledgerCommit(uint256)')
        abort_function = self.contract.get_function_by_signature('interledgerAbort(uint256,uint256)')

        if str(tx_function) == str(commit_function):
            return 'interledgerCommit'

        if str(tx_function) == str(abort_function):
            return 'interledgerAbort'

        return ''

    async def get_interledgerCommit_tx(self, transfer: Transfer):
        return await self.find_function_call(
            'interledgerCommit(uint256)',
            {'id': int(transfer.initiator_id)},
            until=transfer.initiation_timestamp
        )

    async def get_interledgerAbort_tx(self, transfer: Transfer):
        return await self.find_function_call(
            'interledgerAbort(uint256,uint256)',
            {'id': int(transfer.initiator_id)},
            until=transfer.initiation_timestamp
        )

    async def monitor_confirmations(self) -> List[str]:
        function_signatures = [
            str(self.contract.get_function_by_signature('interledgerCommit(uint256)')),
            str(self.contract.get_function_by_signature('interledgerAbort(uint256,uint256)')),
        ]
        block = await self.get_block(
            self.monitor_confirmations_cursor,
            full_transactions=True
        )
        self.monitor_confirmations_cursor = min(
            self.monitor_confirmations_cursor + 1,
            self.web3.eth.blockNumber
        )
        initiator_ids = []
        for tx in block.transactions:
            if tx.to == self.contract.address:
                # decode the input data of the transaction
                tx_function, tx_parameters = self.contract.decode_function_input(tx.input)
                if str(tx_function) in function_signatures:
                    initiator_ids.append(str(tx_parameters['id']))
        return initiator_ids

    async def report_error(self, id: str, reason: int):

        # unlock using the private key
        if self.private_key and not self.isUnlocked(self.minter): # needs to unlock with private key
            transaction = self.contract.functions \
                .interledgerError(Web3.toInt(text=id), reason) \
                .buildTransaction({'from': self.minter})
            transaction.update({'nonce': self.web3.eth.getTransactionCount(self.minter)})
            signed_tx = self.web3.eth.account.signTransaction(transaction, self.private_key)
            abort_tx_hash = self.web3.eth.sendRawTransaction(signed_tx.rawTransaction)
        # unlock using password
        elif self.password is not None:
            unlock = self.web3.geth.personal.unlockAccount(self.minter, self.password, 0) # unlock indefinitely
            if not unlock:
                raise Exception("Wrong password")
            abort_tx_hash = self.contract.functions \
                .interledgerError(Web3.toInt(text=id), reason) \
                .transact({'from': self.minter}) # type uint256 required for id in the smart contract
            # lock the account again
            self.web3.geth.personal.lockAccount(self.minter)
        # no need to unlock
        else:
            abort_tx_hash = self.contract.functions \
                .interledgerError(Web3.toInt(text=id), reason) \
                .transact({'from': self.minter}) # type uint256 required for id in the smart contract
        return await asyncio.get_event_loop().run_in_executor(
            None, functools.partial(self.web3.eth.waitForTransactionReceipt, abort_tx_hash, timeout=self.timeout)
        )

# Responder implementation
class EthereumResponder(Web3Initializer, EthereumCommonMixin, Responder):
    """
    Ethereum implementation of the Responder.
    """

    def __init__(self, cfg: EthereumConfig):
        """
        :param DIBEthereumConfig cfg: config object
        """
        Web3Initializer.__init__(self, cfg.url, cfg.port, cfg.poa, cfg.ipc_path)
        self.contract = self.web3.eth.contract(abi=cfg.contract_abi, address=cfg.contract_address)
        self.last_block = self.web3.eth.blockNumber
        self.private_key = cfg.private_key
        self.minter = cfg.minter
        self.password = cfg.password
        self.timeout=120
        self.ledger_type = LedgerType.ETHEREUM

    async def send_data(self, nonce: str, data: bytes) -> dict:
        """Initiate the interledger receive operation to the connected ledger.

        :param string nonce: the identifier to be unique inside interledger for a data item
        :param string data: the actual content of data in bytes string

        :returns: True if the operation goes well; False otherwise
        :rtype: dict {
            'status': bool,
            'tx_hash': str,     # transaction details
            'blockNumber': int, # transaction details
            'additionalData': int, # transaction details
            'nonce': int,       # transaction details
            'exception': object,# only with errors
            'error_code': Enum, # only with errors
            'message': str      # only with errors
        }
        """
        # Return transaction hash, need to wait for receipt
        tx_hash = None
        tx_receipt = None
        try:
            # unlock using private_key
            if self.private_key and not self.isUnlocked(self.minter): # needs to unlock with private key
                #print("unlock with priv_key")
                transaction = self.contract.functions \
                    .interledgerReceive(Web3.toInt(text=nonce), data) \
                    .buildTransaction({'from': self.minter})
                transaction.update({'nonce': self.web3.eth.getTransactionCount(self.minter)})
                signed_tx = self.web3.eth.account.signTransaction(transaction, self.private_key)
                tx_hash = self.web3.eth.sendRawTransaction(signed_tx.rawTransaction)
            # unlock using password
            elif self.password is not None:
                #print("unlock with password")
                unlock = self.web3.geth.personal.unlockAccount(self.minter, self.password, 0) # unlock indefinitely
                if not unlock:
                    return {"status": False,
                            "error_code": ErrorCode.TRANSACTION_FAILURE,
                            "message": "Wrong password",
                            "tx_hash": None}
                tx_hash = self.contract.functions \
                    .interledgerReceive(Web3.toInt(text=nonce), data) \
                    .transact({'from': self.minter})
                # lock the account again
                self.web3.geth.personal.lockAccount(self.minter)
            # no need to unlock
            else:
                #print("default")
                tx_hash = self.contract.functions \
                    .interledgerReceive(Web3.toInt(text=nonce), data) \
                    .transact({'from': self.minter})
            # tx_receipt = self.web3.eth.waitForTransactionReceipt(tx_hash, timeout=self.timeout)
            return await self.get_send_response(tx_hash.hex(), nonce)
        except web3.exceptions.TimeExhausted as e :
            # Raised by web3.eth.waitForTransactionReceipt
            return {"status": False,
                    "error_code": ErrorCode.TIMEOUT,
                    "message": "Timeout after sending the transaction",
                    "tx_hash": tx_hash.hex(),
                    "exception": e}
        except ValueError as e:
            # Raised by a contract function
            return {"status": False,
                    "error_code": ErrorCode.TRANSACTION_FAILURE,
                    "message": e.__str__(),
                    "tx_hash": tx_hash.hex(),
                    "exception": e}

    async def get_send_response(self, tx_hash: str, nonce: str):
        tx_receipt = await asyncio.get_event_loop().run_in_executor(
            None, functools.partial(self.web3.eth.waitForTransactionReceipt, tx_hash, timeout=self.timeout))

        #print("tx receipt: ", tx_receipt)

        if tx_receipt['status']:
            logs_accept = self.contract.events.InterledgerEventAccepted().processReceipt(tx_receipt)
            logs_reject = self.contract.events.InterledgerEventRejected().processReceipt(tx_receipt)
            if len(logs_reject) != 0 and logs_reject[0]['args']['nonce'] == int(nonce):
                return {"status": False,
                        "error_code": ErrorCode.APPLICATION_REJECT,
                        "message": "InterledgerEventRejected() event received",
                        "tx_hash": tx_hash,
                        "blockNumber": logs_reject[0]['blockNumber'],
                        "additionalData": logs_reject[0]['logIndex'],
                        "nonce": nonce}
            if len(logs_accept) != 0 and logs_accept[0]['args']['nonce'] == int(nonce):
                #print("\t\tsend_data logs: ", logs_accept)
                return {"status": True,
                        "tx_hash": tx_hash,
                        "blockNumber": logs_accept[0]['blockNumber'],
                        "additionalData": logs_accept[0]['logIndex'],
                        "nonce": nonce}
            else:
                return {"status": False,
                        "error_code": ErrorCode.TRANSACTION_FAILURE,
                        "message": "No InterledgerEventAccepted() or InterledgerEventRejected() event received",
                        "tx_hash": tx_hash}
        else:
            # TODO #tx_receipt there is not much documentation about transaction receipt
            # and the values that 'status' can get
            # if a transaction fails, I guess web3py just raises a ValueError exception
            # This return below cannot be clear, but I think it will never be executed
            return {"status": False,
                    "error_code": ErrorCode.TRANSACTION_FAILURE,
                    "message": "Error in the transaction",
                    "tx_hash": tx_hash}

    async def check_response(self, transfer_id: str) -> str:
        event_accepted = (
            self.contract.events
            .InterledgerEventAccepted()
            .createFilter(
                fromBlock=0,  # TODO: fix
                argument_filters={'nonce': Web3.toInt(text=transfer_id)},
            )
        )
        if event_accepted:
            return 'InterledgerEventAccepted'

        event_rejected = (
            self.contract.events
            .InterledgerEventRejected()
            .createFilter(
                fromBlock=0,  # TODO: fix
                argument_filters={'nonce': Web3.toInt(text=transfer_id)},
            )
        )
        if event_rejected:
            return 'InterledgerEventRejected'

        return ''

    async def get_interledgerReceive_tx(self, transfer: Transfer):
        return await self.find_function_call(
            'interledgerReceive(uint256,bytes)',
            {'nonce': int(transfer.id)},
            until=transfer.initiation_timestamp
        )

    async def report_error(self, nonce: str, reason: int):

        # unlock using the private key
        if self.private_key and not self.isUnlocked(self.minter): # needs to unlock with private key
            transaction = self.contract.functions \
                .interledgerError(Web3.toInt(text=nonce), reason) \
                .buildTransaction({'from': self.minter})
            transaction.update({'nonce': self.web3.eth.getTransactionCount(self.minter)})
            signed_tx = self.web3.eth.account.signTransaction(transaction, self.private_key)
            abort_tx_hash = self.web3.eth.sendRawTransaction(signed_tx.rawTransaction)
        # unlock using password
        elif self.password is not None:
            unlock = self.web3.geth.personal.unlockAccount(self.minter, self.password, 0) # unlock indefinitely
            if not unlock:
                raise Exception("Wrong password")
            abort_tx_hash = self.contract.functions \
                .interledgerError(Web3.toInt(text=nonce), reason) \
                .transact({'from': self.minter})
            # lock the account again
            self.web3.geth.personal.lockAccount(self.minter)
        # no need to unlock
        else:
            abort_tx_hash = self.contract.functions \
                .interledgerError(Web3.toInt(text=nonce), reason) \
                .transact({'from': self.minter})
        return await asyncio.get_event_loop().run_in_executor(
            None, functools.partial(self.web3.eth.waitForTransactionReceipt, abort_tx_hash, timeout=self.timeout)
        )

class EthereumMultiResponder(EthereumResponder, MultiResponder):
    """Similar working unit as EthereumResponder, but should be used under multi-ledger mode only.
    """

    async def send_data_inquire(self, nonce: str, data: bytes) -> dict:
        """Invoke the inquiry operation to the connected ledger
        :param string nonce: the identifier to be unique inside interledger for a data item
        :param bytes data: the actual content of data

        :returns: True if the operation goes well; False otherwise
        :rtype: dict {
            'status': bool,
            'tx_hash': str,
            'exception': object,# only with errors
            'error_code': Enum, # only with errors
            'message': str      # only with errors
        }
        """
        # Return transaction hash, need to wait for receipt
        tx_hash = None
        tx_receipt = None
        try:
            # unlock using private_key
            if self.private_key and not self.isUnlocked(self.minter): # needs to unlock with private key
                #print("unlock with priv_key")
                transaction = self.contract.functions \
                    .interledgerInquire(Web3.toInt(text=nonce), data) \
                    .buildTransaction({'from': self.minter})
                transaction.update({'nonce': self.web3.eth.getTransactionCount(self.minter)})
                signed_tx = self.web3.eth.account.signTransaction(transaction, self.private_key)
                tx_hash = self.web3.eth.sendRawTransaction(signed_tx.rawTransaction)
            # unlock using password
            elif self.password is not None:
                #print("unlock with password")
                unlock = self.web3.geth.personal.unlockAccount(self.minter, self.password, 0) # unlock indefinitely
                if not unlock:
                    return {"status": False,
                            "error_code": ErrorCode.TRANSACTION_FAILURE,
                            "message": "Wrong password",
                            "tx_hash": None}
                tx_hash = self.contract.functions \
                    .interledgerInquire(Web3.toInt(text=nonce), data) \
                    .transact({'from': self.minter})
                # lock the account again
                self.web3.geth.personal.lockAccount(self.minter)
            # no need to unlock
            else:
                #print("default")
                tx_hash = self.contract.functions \
                    .interledgerInquire(Web3.toInt(text=nonce), data) \
                    .transact({'from': self.minter})
            # tx_receipt = self.web3.eth.waitForTransactionReceipt(tx_hash, timeout=self.timeout)
            tx_receipt = await asyncio.get_event_loop().run_in_executor(
                None, functools.partial(self.web3.eth.waitForTransactionReceipt, tx_hash, timeout=self.timeout))

            if tx_receipt['status']:
                logs_accept = self.contract.events.InterledgerInquiryAccepted().processReceipt(tx_receipt)
                logs_reject = self.contract.events.InterledgerInquiryRejected().processReceipt(tx_receipt)
                if len(logs_reject) != 0 and logs_reject[0]['args']['nonce'] == int(nonce):
                    return {"status": False,
                            "error_code": ErrorCode.INQUIRY_REJECT,
                            "message": "InterledgerInquiryRejected() event received",
                            "tx_hash": tx_hash}
                if len(logs_accept) != 0 and logs_accept[0]['args']['nonce'] == int(nonce):
                    return {"status": True,
                            "tx_hash": tx_hash}
                else:
                    return {"status": False,
                            "error_code": ErrorCode.TRANSACTION_FAILURE,
                            "message": "No InterledgerInquiryAccepted() or InterledgerInquiryRejected() event received",
                            "tx_hash": tx_hash}
            else:
                return {"status": False,
                        "error_code": ErrorCode.TRANSACTION_FAILURE,
                        "message": "Error in the transaction",
                        "tx_hash": tx_hash}
        except web3.exceptions.TimeExhausted as e :
            # Raised by web3.eth.waitForTransactionReceipt
            return {"status": False,
                    "error_code": ErrorCode.TIMEOUT,
                    "message": "Timeout after sending the transaction",
                    "tx_hash": tx_hash,
                    "exception": e}
        except ValueError as e:
            # Raised by a contract function
            return {"status": False,
                    "error_code": ErrorCode.TRANSACTION_FAILURE,
                    "message": e.__str__(),
                    "tx_hash": tx_hash,
                    "exception": e}


    async def abort_send_data(self, nonce: str, reason: int) -> dict:
        """Invoke the abort sending operation to the connected ledger
        :param string nonce: the identifier to be unique inside interledger for a data item
        :param int reason: the description on why the data transfer is aborted

        :returns: True if the operation goes well; False otherwise
        :rtype: dict {
            'status': bool,
            'tx_hash': str,
            'exception': object,# only with errors
            'error_code': Enum, # only with errors
            'message': str      # only with errors
        }
        """
        # Return transaction hash, need to wait for receipt
        tx_hash = None
        tx_receipt = None
        try:
            # unlock using private_key
            if self.private_key and not self.isUnlocked(self.minter): # needs to unlock with private key
                #print("unlock with priv_key")
                transaction = self.contract.functions \
                    .interledgerReceiveAbort(Web3.toInt(text=nonce), reason) \
                    .buildTransaction({'from': self.minter})
                transaction.update({'nonce': self.web3.eth.getTransactionCount(self.minter)})
                signed_tx = self.web3.eth.account.signTransaction(transaction, self.private_key)
                tx_hash = self.web3.eth.sendRawTransaction(signed_tx.rawTransaction)
            # unlock using password
            elif self.password is not None:
                #print("unlock with password")
                unlock = self.web3.geth.personal.unlockAccount(self.minter, self.password, 0) # unlock indefinitely
                if not unlock:
                    return {"status": False,
                            "error_code": ErrorCode.TRANSACTION_FAILURE,
                            "message": "Wrong password",
                            "tx_hash": None}
                tx_hash = self.contract.functions \
                    .interledgerReceiveAbort(Web3.toInt(text=nonce), reason) \
                    .transact({'from': self.minter})
                # lock the account again
                self.web3.geth.personal.lockAccount(self.minter)
            # no need to unlock
            else:
                #print("default")
                tx_hash = self.contract.functions \
                    .interledgerReceiveAbort(Web3.toInt(text=nonce), reason) \
                    .transact({'from': self.minter})
            # tx_receipt = self.web3.eth.waitForTransactionReceipt(tx_hash, timeout=self.timeout)
            tx_receipt = await asyncio.get_event_loop().run_in_executor(
                None, functools.partial(self.web3.eth.waitForTransactionReceipt, tx_hash, timeout=self.timeout))

            if tx_receipt['status']:
                logs_accept = self.contract.events.InterledgerEventAccepted().processReceipt(tx_receipt)
                logs_reject = self.contract.events.InterledgerEventRejected().processReceipt(tx_receipt)
                if len(logs_reject) != 0 and logs_reject[0]['args']['nonce'] == int(nonce):
                    return {"status": False,
                            "error_code": ErrorCode.APPLICATION_REJECT,
                            "message": "InterledgerEventRejected() event received",
                            "tx_hash": tx_hash}
                if len(logs_accept) != 0 and logs_accept[0]['args']['nonce'] == int(nonce):
                    return {"status": True,
                            "tx_hash": tx_hash}
                else:
                    return {"status": False,
                            "error_code": ErrorCode.TRANSACTION_FAILURE,
                            "message": "No InterledgerEventAccepted() or InterledgerEventRejected() event received",
                            "tx_hash": tx_hash}
            else:
                return {"status": False,
                        "error_code": ErrorCode.TRANSACTION_FAILURE,
                        "message": "Error in the transaction",
                        "tx_hash": tx_hash}
        except web3.exceptions.TimeExhausted as e :
            # Raised by web3.eth.waitForTransactionReceipt
            return {"status": False,
                    "error_code": ErrorCode.TIMEOUT,
                    "message": "Timeout after sending the transaction",
                    "tx_hash": tx_hash,
                    "exception": e}
        except ValueError as e:
            # Raised by a contract function
            return {"status": False,
                    "error_code": ErrorCode.TRANSACTION_FAILURE,
                    "message": e.__str__(),
                    "tx_hash": tx_hash,
                    "exception": e}
