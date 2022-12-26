from __future__ import annotations

from typing import TYPE_CHECKING, Any

import discord_typings as dt

from ...enums import ChannelTypes
from .user import User

if TYPE_CHECKING:
    from ..cache import Cache


class Channel:
    def __init__(self, payload: dt.ChannelData, cache: Cache):
        self.cache = cache
        self._from_data(payload)

    def _from_data(self, payload: dt.ChannelData):
        self._id = payload.get("id")
        self._type = payload.get("type")

    @property
    def id(self) -> int:
        return int(self._id)

    @property
    def type(self) -> ChannelTypes:
        return ChannelTypes(self._type)


class TextChannel(Channel):
    def __init__(self, payload: dt.TextChannelData, cache: Cache):
        super().__init__(payload, cache)
        self._payload = payload

    @property
    def name(self) -> str:
        return self._payload.get("name")

    @property
    def guild(self):
        return self.cache.get_guild(self._payload.get("guild_id"))


class DMChannel(Channel):
    def __init__(self, payload: dt.DMChannelData, cache: Cache):
        super().__init__(payload, cache)
        self._payload = payload

    def set_recipients(self):
        self.recipients = []

        for recipient in self._payload["recipients"]:
            self.recipients.append(User(recipient, self.cache))


def check_channel_type(data: Any, cache: "Cache"):
    type = data["type"]

    if type == ChannelTypes.GUILD_TEXT:
        return TextChannel(data, cache)
    elif type == ChannelTypes.DM:
        return DMChannel(data, cache)
