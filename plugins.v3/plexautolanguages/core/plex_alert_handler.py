from __future__ import annotations

from queue import Queue, Empty
from threading import Thread, Event
from time import sleep
from typing import TYPE_CHECKING

from requests.exceptions import ReadTimeout
from urllib3.exceptions import ReadTimeoutError

from app.sdk.logging import logger

from .alerts import PlexActivity, PlexTimeline, PlexPlaying, PlexStatus

if TYPE_CHECKING:
    from .plex_server import PlexServer

class PlexAlertHandler:

    def __init__(self, plex: PlexServer, trigger_on_play: bool, trigger_on_scan: bool, trigger_on_activity: bool):
        self._plex = plex
        self._trigger_on_play = trigger_on_play
        self._trigger_on_scan = trigger_on_scan
        self._trigger_on_activity = trigger_on_activity
        self._alerts_queue = Queue()
        self._stop_event = Event()
        self._processor_thread = Thread(target=self._process_alerts)
        self._processor_thread.daemon = True
        self._processor_thread.start()

    def stop(self):
        self._stop_event.set()
        self._processor_thread.join(timeout=10)
        if self._processor_thread.is_alive():
            logger.warning("Plex告警处理线程未在 10 秒内停止")

    def __call__(self, message: dict):
        alert_class = None
        alert_field = None
        if self._trigger_on_play and message["type"] == "playing":
            alert_class = PlexPlaying
            alert_field = "PlaySessionStateNotification"
        elif self._trigger_on_activity and message["type"] == "activity":
            alert_class = PlexActivity
            alert_field = "ActivityNotification"
        elif self._trigger_on_scan and message["type"] == "timeline":
            alert_class = PlexTimeline
            alert_field = "TimelineEntry"
        elif self._trigger_on_scan and message["type"] == "status":
            alert_class = PlexStatus
            alert_field = "StatusNotification"

        if alert_class is None or alert_field is None or alert_field not in message:
            return

        for alert_message in message[alert_field]:
            alert = alert_class(alert_message)
            self._alerts_queue.put(alert)

    def _process_alerts(self):
        logger.debug("Starting alert processing thread")
        retry_counter = 0
        alert = None
        while not self._stop_event.is_set():
            try:
                if retry_counter == 0:
                    alert = self._alerts_queue.get(True, 1)
                if alert is None:
                    continue
                try:
                    alert.process(self._plex)
                    retry_counter = 0
                except (ReadTimeout, ReadTimeoutError):
                    retry_counter += 1
                    logger.warning(
                        f"ReadTimeout while processing {alert.TYPE} alert, retrying (attempt {retry_counter})...")
                    logger.debug(alert.message)
                    sleep(1)
                except Exception:
                    logger.error(f"Unable to process {alert.TYPE}", exc_info=True)
                    logger.debug(alert.message)
                    retry_counter = 0
            except Empty:
                pass
        logger.debug("Stopping alert processing thread")
