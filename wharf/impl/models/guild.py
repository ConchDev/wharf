import discord_typings as dt
from typing import TYPE_CHECKING

from .member import Member

if TYPE_CHECKING:
    from ...client import Client
    


class Guild:
    def __init__(self, data: dt.GuildData, bot: 'Client'):
        self._from_data(data)
        self.bot = bot

    def _from_data(self, guild: dt.GuildData):
        self.name = guild.get("name")
        self.id = guild.get("id")
        self.icon_hash = guild.get("icon")

    async def fetch_member(self, user: int):
        return Member(await self.bot.http.get_member(user, self.id))