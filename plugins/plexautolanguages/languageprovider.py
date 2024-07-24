import logging
from pathlib import Path
from time import sleep

from websocket import WebSocketConnectionClosedException

from app.plugins.plexautolanguages.core.plex_server import PlexServer
from app.plugins.plexautolanguages.core.utils.configuration import Configuration


class LanguageProvider:

    def __init__(self, default_config_path: Path, user_config_path: Path, logger: logging.Logger):
        self.alive = False
        self.must_stop = False
        self.stop_signal = False
        self.plex_alert_listener = None
        self.logger = logger

        # Configuration
        self.config = Configuration(default_config_path, user_config_path)

        # Notifications
        self.notifier = None
        # if self.config.get("notifications.enable"):
        #     self.notifier = Notifier(self.config.get("notifications.apprise_configs"))

        # Scheduler
        self.scheduler = None
        # if self.config.get("scheduler.enable"):
        #     self.scheduler = Scheduler(self.config.get("scheduler.schedule_time"), self.scheduler_callback)

        # Plex
        self.plex = None

    def init(self):
        try:
            self.plex = PlexServer(self.config.get("plex.url"),
                                   self.config.get("plex.token"),
                                   self.notifier,
                                   self.config)
        except Exception as e:
            self.logger.error(e)

    def is_ready(self):
        return self.alive

    def is_healthy(self):
        return self.alive and self.plex.is_alive

    def stop(self, *_):
        self.logger.info("Received SIGINT or SIGTERM, stopping gracefully")
        self.must_stop = True
        self.stop_signal = True

    def start(self):
        if self.scheduler:
            self.scheduler.start()

        while not self.stop_signal:
            self.must_stop = False
            self.init()
            if self.plex is None:
                break
            self.plex.start_alert_listener(self.alert_listener_error_callback)
            self.alive = True
            count = 0
            while not self.must_stop:
                sleep(1)
                count += 1
                if count % 60 == 0 and not self.plex.is_alive:
                    self.logger.warning("Lost connection to the Plex server")
                    self.must_stop = True
            self.alive = False
            self.plex.save_cache()
            self.plex.stop()
            if not self.stop_signal:
                sleep(1)
                self.logger.info("Trying to restore the connection to the Plex server...")

        if self.scheduler:
            self.scheduler.shutdown()
            self.scheduler.join()

    def alert_listener_error_callback(self, error: Exception):
        if isinstance(error, WebSocketConnectionClosedException):
            self.logger.warning("The Plex server closed the websocket connection")
        elif isinstance(error, UnicodeDecodeError):
            self.logger.debug("Ignoring a websocket payload that could not be decoded")
            return
        else:
            self.logger.error("Alert listener had an unexpected error")
            self.logger.error(error, exc_info=True)
        self.must_stop = True

    def scheduler_callback(self):
        if self.plex is None or not self.plex.is_alive:
            return
        self.logger.info("Starting scheduler task")
        self.plex.start_deep_analysis()
