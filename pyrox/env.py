import os
import logging

from pyrox.config import get_config


_LOG_LEVEL_NOTSET = 'NOTSET'


class LoggingManager(object):

    def __init__(self, cfg):
        self._root_logger = logging.getLogger()
        self._handlers = list()

    def _add_handler(self, handler):
        self._handlers.append(handler)
        self._root_logger.addHandler(handler)

    def configure(self, cfg):
        # Remove previous handlers
        # TODO:Review - Not sure if this is the best idea...?
        [self._root_logger.removeHandler(hdlr) for hdlr in self._handlers]
        del self._handlers[:]

        # Configuration handling
        self._root_logger.setLevel(cfg.logging.verbosity)
        if cfg.logging.logfile:
            self._add_handler(logging.FileHandler(cfg.logging.logfile))
        if cfg.logging.console:
            self._add_handler(logging.StreamHandler())

    def get_logger(logger_name):
        logger = logging.getLogger(logger_name)
        logger.setLevel(_LOG_LEVEL_NOTSET)
        return logger


def set_log_file(logfile):
    globals()['_LOGFILE'] = logfile

def get_logger(logger_name):
    conf = get_config()
    logger = logging.getLogger(logger_name)
    logger.setLevel(_DEFAULT_LOG_LEVEL)
    logger.propagate = False

    if _LOGFILE:
        file_handler = logging.FileHandler(_LOGFILE)
        logger.addHandler(file_handler)
    logger.addHandler(_CONSOLE_STREAM)
    return logger


def get(name, default=None):
    value = os.env.get(name)
    return value if value else default


_init()
