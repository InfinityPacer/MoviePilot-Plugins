from __future__ import annotations
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.plugins.plexautolanguages.core.plex_server import PlexServer


class PlexAlert():

    TYPE = None

    def __init__(self, message: dict):
        self._message = message

    @property
    def message(self):
        return self._message

    def process(self, plex: PlexServer):
        raise NotImplementedError
