import asyncio
import warnings

from hashlib import md5
from time import time
from typing import (
    Dict,
    List,
    Tuple,
    Optional,
)

from .transfer import Transfer
from .utils import Logger


SUPPRESS_WARNINGS = True


class DecentralizedInterledger:

    def __init__(self, initiator, responder, config):
        self.initiator = initiator
        self.responder = responder
        self.config = config

        self.background_tasks = set()
        self.transfer_register: Dict[Transfer] = {}
        self.running = False

        self.initiator.secret = self.config.secret
        self.responder.secret = self.config.secret

        Logger.init(node_id=self.config.node_id)
        self.time_previous = 0

    def run_in_background(self, coroutine):
        task = asyncio.create_task(coroutine)

        # Add task to the set. This creates a strong reference.
        self.background_tasks.add(task)

        # To prevent keeping references to finished tasks forever,
        # make each task remove its own reference from the set after
        # completion:
        task.add_done_callback(self.background_tasks.discard)

    def register_transfer(self, transfer: Transfer):
        self.transfer_register[transfer.id] = transfer

    def deregister_transfer(self, transfer_id: str) -> Transfer:
        return self.transfer_register.pop(transfer_id, None)

    def find_transfer_by_initiator_id(self, initiator_id: str) -> Optional[Transfer]:
        for transfer in list(self.transfer_register.values()):
            if transfer.initiator_id == initiator_id:
                return transfer

    def get_transfer_age(self, transfer: Transfer) -> int:
        return (time() - transfer.initiation_timestamp)

    def resolve_timeout_period(self, target_time, period_idx=0):
        backoff_factor = self.config.timeout_backoff ** period_idx  # exponent
        period_duration = self.config.timeout_initial * backoff_factor
        if target_time < period_duration:
            time_left = period_duration - target_time
            return period_idx, period_duration, time_left
        return self.resolve_timeout_period(
            target_time - period_duration,
            period_idx + 1
        )

    def is_my_duty(self, transfer: Transfer) -> bool:
        transfer_age = self.get_transfer_age(transfer)
        period_idx, period_duration, time_left = self.resolve_timeout_period(transfer_age)
        if time_left < (period_duration / 2):
            return False
        increment = period_idx % self.config.node_count
        transfer_id = 0 if self.config.route_to_first_node else int(transfer.id)
        node_id = ((transfer_id + increment) % self.config.node_count) + 1
        return node_id == self.config.node_id

    def is_timed_out(self, transfer: Transfer) -> bool:
        transfer_age = self.get_transfer_age(transfer)
        period_idx, *_ = self.resolve_timeout_period(transfer_age)
        return (0 < period_idx)

    def get_timed_out_transfers(self) -> List[Transfer]:
        return [
            t for t in list(self.transfer_register.values())
            if self.is_timed_out(t) and self.is_my_duty(t)
        ]

    async def execute_transfer(self, transfer: Transfer):
        Logger.log(transfer.short_id)
        response = await self.responder.send_data(transfer.id, transfer.data)
        if self.config.confirm_transfer and response['status'] is True:
            await self.confirm_transfer(transfer, response.get('error_code'))

    async def confirm_transfer(self, transfer: Transfer, error: int):
        if error:
            Logger.log('abort:', transfer.short_id)
            await self.initiator.abort_sending(transfer.initiator_id, error)
        else:
            Logger.log('commit:', transfer.short_id)
            await self.initiator.commit_sending(transfer.initiator_id)
        self.deregister_transfer(transfer.id)

    async def get_responder_ack(self, transfer: Transfer) -> Tuple[str, dict]:
        ack = await self.responder.check_response(transfer.id)

        if ack == 'InterledgerEventAccepted':
            Logger.log('InterledgerEventAccepted')
            tx = await self.initiator.get_interledgerCommit_tx(transfer)
        elif ack == 'InterledgerEventRejected':
            Logger.log('InterledgerEventRejected')
            tx = await self.initiator.get_interledgerAbort_tx(transfer)
        else:
            Logger.log('InterledgerEventAccepted or InterledgerEventRejected missing!')
            return '', {}

        return ack, tx

    async def verify_transfer(self, transfer: Transfer):
        Logger.log(transfer.short_id)

        responder_tx = await self.responder.get_interledgerReceive_tx(transfer)

        # check that transfered data match
        responder_data = responder_tx['txParams']['data']
        data_match = transfer.data == responder_data

        # check that ack from responder to initiator matches
        responder_ack, final_tx = await self.get_responder_ack(transfer)
        initiator_ack = await self.initiator.check_confirmation(final_tx)

        ack_match = (
            (responder_ack == 'InterledgerEventAccepted'
            and
            initiator_ack == 'interledgerCommit')
            or
            (responder_ack == 'InterledgerEventRejected'
            and
            initiator_ack == 'interledgerAbort')
        )

        is_valid = data_match and ack_match

        Logger.log('valid:', is_valid)

        if not is_valid:
            if not data_match:
                Logger.log('data:', transfer.data, responder_data)
            if not ack_match:
                Logger.log(
                    'initiator_ack:', initiator_ack,
                    'responder_ack:', responder_ack,
                )
            reason = int(md5(b'INVALID_TRANSFER').hexdigest(), 16)
            await self.initiator.report_error(transfer.initiator_id, reason)
            await self.responder.report_error(transfer.id, reason)
            Logger.log('INVALID TRANSFER:', transfer.id)

        self.deregister_transfer(transfer.id)

    async def process_initiator_event(self, event):
        transfer = await self.initiator.process_event(event)
        self.register_transfer(transfer)
        Logger.log(f"transfer {transfer.short_id} registered")

        if self.is_my_duty(transfer):
            await self.execute_transfer(transfer)

    async def process_initiator_events(self):
        # new transfer from initiator
        events = await self.initiator.listen_for_events()
        tasks = [asyncio.create_task(self.process_initiator_event(e)) for e in events]
        await asyncio.gather(*tasks)

    async def process_timeout(self, transfer: Transfer):
        Logger.log('transfer id:', transfer.short_id)

        # 1. transfer not sent

        send_tx = await self.responder.get_interledgerReceive_tx(transfer)

        if not send_tx:
            Logger.log('transfer not sent')
            await self.execute_transfer(transfer)
            return

        # 1.2. transfer sent but event not received
        ack, ack_tx = await self.get_responder_ack(transfer)
        if not ack:
            return  # vague problem, report to client

        # 2. transfer not acknowledged to initiator
        # 2.a) transfer committed
        # 2.b) transfer aborted

        if not ack_tx:
            Logger.log('transfer not acknowledged to initiator')
            response = await self.responder.get_send_response(
                send_tx['txID'], transfer.id
            )
            await self.confirm_transfer(transfer, response.get('error_code'))
            return

        Logger.log('transfer acknowledged to initiator')

    async def process_timeouts(self):
        transfers = self.get_timed_out_transfers()
        tasks = [self.process_timeout(t) for t in transfers]
        await asyncio.gather(*tasks)

    async def process_verifications(self):
        initiator_ids = await self.initiator.monitor_confirmations()
        tasks = []
        for initiator_id in initiator_ids:
            transfer = self.find_transfer_by_initiator_id(initiator_id)
            if transfer:
                task = asyncio.create_task(
                    self.verify_transfer(transfer)
                )
                tasks.append(task)
        await asyncio.gather(*tasks)

    def print_transfer_register(self):
        time_now = int(time() / 10)
        if time_now > self.time_previous:
            self.time_previous = time_now
            Logger.log(self.transfer_register)

    async def _run(self):
        while self.running:
            # NOTE! don't change the order, unless you know what you are doing
            await self.process_initiator_events()
            if self.config.verification_enabled:
                await self.process_verifications()
            if self.config.timeout_enabled:
                await self.process_timeouts()
            self.print_transfer_register()

    async def run(self):
        print("*******************************************")
        print("DIL running...")
        print("*******************************************")
        self.running = True

        if SUPPRESS_WARNINGS:
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                await self._run()
        else:
            await self._run()

    def stop(self):
        """Stop the interledger run() operation
        """
        print("*******************************************")
        print("DIL stopped...")
        print("*******************************************")
        self.running = False
