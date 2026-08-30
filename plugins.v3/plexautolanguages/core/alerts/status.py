from __future__ import annotations
from typing import TYPE_CHECKING

from ..constants import EventType
from app.sdk.logging import logger
from .base import PlexAlert

if TYPE_CHECKING:
    from ..plex_server import PlexServer


class PlexStatus(PlexAlert):

    TYPE = "status"

    @property
    def title(self):
        return self._message.get("title", None)

    def process(self, plex: PlexServer):
        if self.title != "Library scan complete":
            return
        logger.debug("[Status] The Plex server scanned the library")

        if plex.config.get("refresh_library_on_scan"):
            added, updated = plex.cache.refresh_library_cache()
        else:
            added = plex.get_recently_added_episodes(minutes=5)
            updated = []

        # Process recently added episodes
        if len(added) > 0:
            logger.debug(f"[Status] Found {len(added)} newly added episode(s)")
            for item in added:
                # Check if the item should be ignored
                if plex.should_ignore_show(item.show()):
                    continue

                # Check if the item has already been processed
                if not plex.cache.should_process_recently_added(item.key, item.addedAt):
                    continue

                # Change tracks for all users
                logger.info(f"[Status] Processing newly added episode {plex.get_episode_short_name(item)}")
                plex.process_new_or_updated_episode(item.key, EventType.NEW_EPISODE, True)

        # Process updated episodes
        if len(updated) > 0:
            logger.debug(f"[Status] Found {len(updated)} updated episode(s)")
            for item in updated:
                # Check if the item should be ignored
                if plex.should_ignore_show(item.show()):
                    continue

                # Check if the item has already been processed
                if not plex.cache.should_process_recently_updated(item.key):
                    continue

                # Change tracks for all users
                logger.info(f"[Status] Processing updated episode {plex.get_episode_short_name(item)}")
                plex.process_new_or_updated_episode(item.key, EventType.UPDATED_EPISODE, False)
