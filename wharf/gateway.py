from __future__ import annotations

import asyncio
import random
from sys import platform as _os
import time
from aiohttp import ClientWebSocketResponse, WSMsgType, WSMessage

from typing import TYPE_CHECKING, Optional, Dict, Any, cast

import json

import logging

from zlib import decompressobj

from .types.gateway import GatewayData

if TYPE_CHECKING:
    from .impl import Cache
    from .dispatcher import Dispatcher


DEFAULT_API_VERSION = 10

_log = logging.getLogger(__name__)

class OPCodes:
    DISPATCH = 0
    HEARTBEAT = 1
    IDENTIFY = 2
    PRESENCE_UPDATE = 3
    VOICE_STATE_UPDATE = 4
    RESUME = 6
    RECONNECT = 7
    REQUEST_GUILD_MEMBERS = 8
    INVALID_SESSION = 9
    HELLO = 10
    HEARTBEAT_ACK = 11


class Gateway: # This Class is in no way supposed to be used by itself. it should ALWAYS be used with `wharf.Bot`. so seriously, dont :sob:
    if TYPE_CHECKING:
        ws: ClientWebSocketResponse
        heartbeat_interval: int
        resume_url: str
        last_sequence: int

    def __init__(self, dispatcher: Dispatcher, cache: Cache):
        self._dispatcher = dispatcher
        self._cache = cache
        self._http = self._cache.http

        # Defining token and intents
        self.token = self._cache.http._token
        self.intents = self._cache.http._intents

        self.inflator = decompressobj()

        self.resume: bool = False
        self._first_heartbeat = True

    def decompress_data(self, data: bytes):
        ZLIB_SUFFIX = b"\x00\x00\xff\xff"

        out_str: str = ""

        # Message should be compressed
        if len(data) < 4 or data[-4:] != ZLIB_SUFFIX:
            return out_str

        buff = self.inflator.decompress(data)
        out_str = buff.decode("utf-8")

        return out_str

    @property
    def ping_payload(self):
        payload = {
            "op": OPCodes.HEARTBEAT, "d": self.last_sequence            
        }

        return payload

    @property
    def identify_payload(self):
        payload = {
            "op": OPCodes.IDENTIFY,
            "d": {
                "token": self.token,
                "intents": self.intents,
                "properties": {
                    "os": _os,
                    "browser": "wharf",
                    "device": "wharf"
                },
                "large_threshold": 250
            }
        }
        
        return payload

    async def send(self, payload: Dict[str, Any]):
        if not self.ws:
            return

        await self.ws.send_json(payload)

        _log.debug("Sent payload json %s to the gateway.", payload)

    async def receive(self):
        if not self.ws:
            return
        
        msg: WSMessage = await self.ws.receive()

        if msg.type in (WSMsgType.TEXT, WSMsgType.BINARY):
            received_msg: str

            if msg.type == WSMsgType.BINARY:
                received_msg = self.decompress_data(msg.data)
            else:
                received_msg = cast(str, msg.data)

            self.gateway_payload = cast(GatewayData, json.loads(received_msg))

            self.last_sequence = self.gateway_payload.get("s")

            return True

    async def keep_heartbeat(self):
        jitters = self.heartbeat_interval
        if self._first_heartbeat:
            jitters *= random.uniform(1.0, 0.0)
            self._first_heartbeat = False

        await self.ws.send_json(self.ping_payload)
        await asyncio.sleep(jitters / 1000)
        asyncio.create_task(self.keep_heartbeat())
    
    async def connect(self, url: Optional[str] = None):
        if not url:
            url = (await self._http.get_gateway_bot())["url"]

        self.ws = await self._http._session.ws_connect(url) # type: ignore

        msg = await self.receive()

        if msg and self.gateway_payload is not None:
            if self.gateway_payload["op"] == OPCodes.HELLO:
                self.heartbeat_interval = self.gateway_payload["d"]["heartbeat_interval"]

        asyncio.create_task(self.keep_heartbeat())

        await self.send(self.identify_payload)

        return await self.listen_for_events()

    async def listen_for_events(self):
        if not self.ws:
            return
        
        while not self.is_closed:
            res = await self.receive()

            _log.info(self.gateway_payload["d"])

            if res and self.gateway_payload is not None:
                if self.gateway_payload["op"] == OPCodes.DISPATCH:
                    if self.gateway_payload["t"] == "READY":
                        self.session_id = self.gateway_payload["d"]["session_id"]
                        self.resume_url = self.gateway_payload["d"]["resume_gateway_url"]

                    # As messy as this all is, this probably is best here.
                    if self.gateway_payload["t"] == "GUILD_CREATE":
                        asyncio.create_task(self._cache._handle_guild_caching(self.gateway_payload["d"]))

                    elif self.gateway_payload["t"] == "GUILD_MEMBER_ADD":
                        self._cache.add_member(int(self.gateway_payload["d"]["guild_id"]), self.gateway_payload["d"])

                    elif self.gateway_payload["t"] == "GUILD_DELETE":
                        self._cache.remove_guild(int(self.gateway_payload["d"]["id"]))

                    elif self.gateway_payload["t"] == "GUILD_MEMBER_REMOVE":
                        self._cache.remove_member(
                            int(self.gateway_payload["d"]["guild_id"]), int(self.gateway_payload["d"]["user"]["id"])
                        )

                    elif self.gateway_payload["t"] == "CHANNEL_DELETE":
                        self._cache.remove_channel(
                            int(self.gateway_payload["d"]["guild_id"]), int(self.gateway_payload["d"]["id"])
                        )

                    else:
                        if self.gateway_payload["t"].lower() not in self._dispatcher.events.keys():
                            continue

                        self._dispatcher.dispatch(self.gateway_payload["t"].lower(), self.gateway_payload["d"])
            
            elif self.gateway_payload["op"] == OPCodes.HEARTBEAT:
                await self.send(self.ping_payload)

            elif self.gateway_payload["op"] == OPCodes.HEARTBEAT_ACK:
                self._last_heartbeat_ack = time.perf_counter()

                _log.info("Awknoledged heartbeat!")

    @property
    def is_closed(self) -> bool:
        if not self.ws:
            return False

        return self.ws.closed
        


        

