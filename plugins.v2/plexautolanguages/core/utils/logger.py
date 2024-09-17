import logging
from pathlib import Path

from app.log import logger


class CustomFormatter:
    grey = "\x1b[38;21m"
    blue = "\x1b[38;5;39m"
    yellow = "\x1b[38;5;226m"
    red = "\x1b[38;5;196m"
    bold_red = "\x1b[31;1m"
    reset = "\x1b[0m"
    fmt = "%(asctime)s [%(levelname)s] %(message)s"

    FORMATS = {
        logging.DEBUG: grey + fmt + reset,
        logging.INFO: blue + fmt + reset,
        logging.WARNING: yellow + fmt + reset,
        logging.ERROR: red + fmt + reset,
        logging.CRITICAL: bold_red + fmt + reset
    }

    def format(self, record):
        log_fmt = self.FORMATS.get(record.levelno)
        formatter = logging.Formatter(log_fmt)
        return formatter.format(record)


def get_logger(plugin_name: str = None):
    """
    获取模块的logger
    """
    return logger
    # if plugin_name:
    #     loggers = getattr(logger, '_loggers', None)
    #     if loggers:
    #         logfile = Path("plugins") / f"{plugin_name}.log"
    #         _logger = loggers.get(logfile)
    #         if _logger:
    #             return _logger
    # return logging.getLogger(__name__)
