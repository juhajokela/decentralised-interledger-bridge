import asyncio
import itertools

from time import sleep

from hfc.fabric import Client
from hfc.fabric.peer import Peer
from hfc.fabric.transaction.tx_context import create_tx_context
from hfc.fabric.transaction.tx_proposal_request import (
    create_tx_prop_req,
    CC_TYPE_GOLANG,
    CC_INVOKE
)
from hfc.fabric.block_decoder import decode_proposal_response_payload
from hfc.util import utils

from grpc._channel import _MultiThreadedRendezvous


class FabricClient(Client):

    async def chaincode_invoke(self, requestor, channel_name, peers, args,
                               cc_name,
                               cc_type=CC_TYPE_GOLANG,
                               fcn='invoke',
                               transient_map=None,
                               wait_for_event=False,
                               wait_for_event_timeout=30,
                               grpc_broker_unavailable_retry=0,
                               grpc_broker_unavailable_retry_delay=3000,  # ms
                               raise_broker_unavailable=True):
        """
        Invoke chaincode for ledger update
        :param requestor: User role who issue the request
        :param channel_name: the name of the channel to send tx proposal
        :param peers: List of  peer name and/or Peer to install
        :param args (list): arguments (keys and values) for initialization
        :param cc_name: chaincode name
        :param cc_type: chaincode type language
        :param fcn: chaincode function
        :param transient_map: transient map
        :param wait_for_event: Whether to wait for the event from each peer's
         deliver filtered service signifying that the 'invoke' transaction has
          been committed successfully
        :param wait_for_event_timeout: Time to wait for the event from each
         peer's deliver filtered service signifying that the 'invoke'
          transaction has been committed successfully (default 30s)
        :param grpc_broker_unavailable_retry: Number of retry if a broker
         is unavailable (default 0)
        :param grpc_broker_unavailable_retry_delay : Delay in ms to retry
         (default 3000 ms)
        :param raise_broker_unavailable: Raise if any broker is unavailable,
         else always send the proposal regardless of unavailable brokers.
        :return: invoke result
        """
        target_peers = []
        for peer in peers:
            if isinstance(peer, Peer):
                target_peers.append(peer)
            elif isinstance(peer, str):
                peer = self.get_peer(peer)
                target_peers.append(peer)
            else:
                _logger.error(f'{peer} should be a peer name or '
                              f'a Peer instance')

        if not target_peers:
            err_msg = 'Failed to query block: no functional peer provided'
            _logger.error(err_msg)
            raise Exception(err_msg)

        tran_prop_req = create_tx_prop_req(
            prop_type=CC_INVOKE,
            cc_name=cc_name,
            cc_type=cc_type,
            fcn=fcn,
            args=args,
            transient_map=transient_map
        )

        tx_context = create_tx_context(
            requestor,
            requestor.cryptoSuite,
            tran_prop_req
        )

        channel = self.get_channel(channel_name)

        # send proposal
        responses, proposal, header = channel.send_tx_proposal(tx_context, target_peers)

        # The proposal return does not contain the transient map
        # because we do not sent it in the real transaction later
        res = await asyncio.gather(*responses, return_exceptions=True)
        failed_res = list(map(lambda x: isinstance(x, _MultiThreadedRendezvous), res))

        # remove failed_res from res, orderer will take care of unmet policy (can be different between app,
        # you should costumize this method to your own needs)
        if any(failed_res):
            res = list(filter(lambda x: hasattr(x, 'response') and x.response.status == 200, res))

            # should we retry on failed?
            if grpc_broker_unavailable_retry:
                _logger.debug('Retry on failed proposal responses')

                retry = 0

                # get failed peers
                failed_target_peers = list(itertools.compress(target_peers, failed_res))

                while retry < grpc_broker_unavailable_retry:
                    _logger.debug(f'Retrying getting proposal responses from peers:'
                                  f' {[x.name for x in failed_target_peers]}, retry: {retry}')

                    retry_responses, _, _ = channel.send_tx_proposal(tx_context, failed_target_peers)
                    retry_res = await asyncio.gather(*retry_responses, return_exceptions=True)

                    # get failed res
                    failed_res = list(map(lambda x: isinstance(x, _MultiThreadedRendezvous), retry_res))

                    # add successful responses to res and recompute failed_target_peers
                    res += list(filter(lambda x: hasattr(x, 'response') and x.response.status == 200, retry_res))
                    failed_target_peers = list(itertools.compress(failed_target_peers, failed_res))

                    if len(failed_target_peers) == 0:
                        break

                    retry += 1
                    # TODO should we use a backoff?
                    _logger.debug(f'Retry in {grpc_broker_unavailable_retry_delay}ms')
                    sleep(grpc_broker_unavailable_retry_delay / 1000)  # milliseconds

                if len(failed_target_peers) > 0:
                    if raise_broker_unavailable:
                        raise Exception(f'Could not reach peer grpc broker {[x.name for x in failed_target_peers]}'
                                        f' even after {grpc_broker_unavailable_retry} retries.')
                    else:
                        _logger.debug(f'Could not reach peer grpc broker {[x.name for x in failed_target_peers]}'
                                      f' even after {grpc_broker_unavailable_retry} retries.')
                else:
                    _logger.debug('Proposals retrying successful.')

        # if proposal was not good, return
        if any([x.response.status != 200 for x in res]):
            return '; '.join({x.response.message for x in res
                              if x.response.status != 200})

        # send transaction to the orderer
        tran_req = utils.build_tx_req((res, proposal, header))
        tx_context_tx = create_tx_context(
            requestor,
            requestor.cryptoSuite,
            tran_req
        )

        # wait for transaction id proposal available in ledger and block
        # commited
        if wait_for_event:
            # wait for event
            self.evt_tx_id = tx_context.tx_id
            self.evts = {}
            event_stream = []

            for target_peer in target_peers:
                channel_event_hub = channel.newChannelEventHub(target_peer,
                                                               requestor)
                stream = channel_event_hub.connect()
                event_stream.append(stream)

                txid = channel_event_hub.registerTxEvent(
                    self.evt_tx_id,
                    unregister=True,
                    disconnect=True,
                    onEvent=self.txEvent)

                if txid not in self.evts:
                    self.evts[txid] = {'channel_event_hubs': []}

                self.evts[txid]['channel_event_hubs'] +=\
                    [channel_event_hub]

        # response is a stream
        response = utils.send_transaction(self.orderers, tran_req,
                                          tx_context_tx)

        async for v in response:
            if not v.status == 200:
                return v.message

        if wait_for_event:
            try:
                await asyncio.wait_for(asyncio.gather(*event_stream,
                                                      return_exceptions=True),
                                       timeout=wait_for_event_timeout)
            except asyncio.TimeoutError:
                for k, v in self.evts.items():
                    for x in v['channel_event_hubs']:
                        x.unregisterTxEvent(k)
                raise TimeoutError('waitForEvent timed out.')
            except Exception as e:
                raise e
            else:
                # check if all tx are valids
                txEvents = self.evts[self.evt_tx_id]['txEvents']
                statuses = [x['tx_status'] for x in txEvents]
                if not all([x == 'VALID' for x in statuses]):
                    raise Exception(statuses)
            finally:
                # disconnect channel_event_hubs
                cehs = self.evts[self.evt_tx_id]['channel_event_hubs']
                for x in cehs:
                    x.disconnect()

        res = decode_proposal_response_payload(res[0].payload)
        return res['extension']['response']['payload'].decode('utf-8')
