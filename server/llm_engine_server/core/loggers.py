import contextvars
import inspect
import logging
import os
import sys
import warnings
from contextlib import contextmanager
from typing import Optional, Sequence

import ddtrace
import json_log_formatter
import tqdm
from ddtrace.helpers import get_correlation_ids

# DO NOT CHANGE LOGGING FORMAT
LOG_FORMAT: str = "%(asctime)s %(levelname)s [%(name)s] [%(filename)s:%(lineno)d] - %(message)s"
# REQUIRED FOR DATADOG COMPATIBILITY

ctx_var_request_id = contextvars.ContextVar("ctx_var_request_id", default=None)

__all__: Sequence[str] = (
    # most common imports
    "make_logger",
    "logger_name",
    # supporting / less common
    "make_standard_logger",
    "deprecation_warning",
    "make_json_logger",
    "LOG_FORMAT",
    "CustomJSONFormatter",
    "TqdmLoggingHandler",
    "print_logger",
    "silence_chatty_datadog_loggers",
    "silence_chatty_logger",
    "loggers_at_level",
    # utils
    "filename_wo_ext",
    "get_request_id",
    "set_request_id",
)


def get_request_id() -> Optional[str]:
    """Get the request id from the context variable."""
    return ctx_var_request_id.get()


def set_request_id(request_id: str) -> None:
    """Set the request id in the context variable."""
    ctx_var_request_id.set(request_id)


def make_standard_logger(name: str, log_level: int = logging.INFO) -> logging.Logger:
    """Standard protocol for creating a logger that works well with Datadog & local development.

    Interoperates with the log formatting performed by Datadog's `ddtrace-run` program.
    When running a Python program with `ddtrace-run python ...`, `ddtrace-run` will override
    the logging format set here. Creating a logger using this function will ensure that you
    will be able to always view the logging output on STDERR, with or without running with
    `ddtrace-run`.
    """
    if name is None or not isinstance(name, str) or len(name) == 0:
        raise ValueError("Name must be a non-empty string.")
    logger = logging.getLogger(name)
    logger.setLevel(log_level)
    logging.basicConfig(
        format=LOG_FORMAT,
    )
    return logger


class CustomJSONFormatter(json_log_formatter.JSONFormatter):
    def json_record(self, message: str, extra: dict, record: logging.LogRecord) -> dict:
        extra = super().json_record(message, extra, record)
        extra["level"] = record.levelname
        extra["name"] = record.name
        extra["lineno"] = record.lineno
        extra["pathname"] = record.pathname

        # add the http request id if it exists
        request_id = ctx_var_request_id.get()
        if request_id:
            extra["request_id"] = request_id

        trace_id, span_id = get_correlation_ids()

        # add ids to event dictionary
        extra["dd.trace_id"] = trace_id or 0
        extra["dd.span_id"] = span_id or 0

        # add the env, service, and version configured for the tracer.
        # If tracing is not set up, then this should pull values from DD_ENV, DD_SERVICE, and DD_VERSION.
        service_override = ddtrace.config.service or os.getenv("DD_SERVICE")
        if service_override:
            extra["dd.service"] = service_override

        env_override = ddtrace.config.env or os.getenv("DD_ENV")
        if env_override:
            extra["dd.env"] = env_override

        version_override = ddtrace.config.version or os.getenv("DD_VERSION")
        if version_override:
            extra["dd.version"] = version_override

        return extra


def make_json_logger(name: str, log_level: int = logging.INFO) -> logging.Logger:
    """Create a JSON logger. This allows us to pass arbitrary key/value data in log messages.
    It also puts stack traces in a single log message instead of spreading them across multiple log messages.
    """
    if name is None or not isinstance(name, str) or len(name) == 0:
        raise ValueError("Name must be a non-empty string.")

    logger = logging.getLogger(name)
    if any(isinstance(handler, logging.StreamHandler) for handler in logger.handlers):
        # logger already initialized
        return logger

    stream_handler = logging.StreamHandler()
    in_kubernetes = os.getenv("KUBERNETES_SERVICE_HOST")
    if in_kubernetes:
        # Somewhat hacky way of determining if we're running in a Datadog environment.
        # Note that if you 'kubectl logs' the pod, you'll still see the JSON logs. But you really should
        # just be looking at the logs in Datadog at that point.
        #
        # NOTE: If you're thinking of disabling this outside of your local machine, please consider
        # just piping to `jq` instead, e.g.:
        #
        # $ kubectl logs -lapp=celery-autoscaler-singleton | jq -r '[.time, .level, .message] | join(" - ")'
        #
        # this spits out:
        #
        # 2021-04-08T23:40:03.148308 - INFO - Missing params, skipping deployment : <etc>
        # 2021-04-08T23:40:03.148440 - INFO - Missing params, skipping deployment : <etc>
        stream_handler.setFormatter(CustomJSONFormatter())
    else:
        # Reading JSON logs in your terminal is kinda hard, and you can't make use of the structured data
        # benefits in your terminal anyway. So just fall back to the standard log format.
        stream_handler.setFormatter(logging.Formatter(LOG_FORMAT))

    logger.addHandler(stream_handler)
    logger.setLevel(log_level)

    # Something is creating an extra handler
    logger.propagate = (
        False  # Don't need to set to False as long as you don't also call logging.basicConfig()
    )

    # Want to make sure that unhandled exceptions get logged using the JSON logger. Otherwise,
    # users will have to remember to wrap their main functions with:
    #
    # try:
    #     main()
    # except Exception:
    #     logger.exception("blah")
    #
    # See: https://stackoverflow.com/a/16993115/1729558
    def handle_exception(exc_type, exc_value, exc_traceback):
        if issubclass(exc_type, KeyboardInterrupt):
            sys.__excepthook__(exc_type, exc_value, exc_traceback)
            return

        logger.error("Uncaught exception", exc_info=(exc_type, exc_value, exc_traceback))

    sys.excepthook = handle_exception
    return logger


def make_logger(name: str, log_level: int = logging.INFO) -> logging.Logger:
    return make_json_logger(name, log_level)


def logger_name(*, fallback_name: Optional[str] = None) -> str:
    """Returns the __name__ from where the calling function is defined or its filename if it is "__main__".

    Normally, __name__ is the fully qualified Python name of the module. However, if execution starts at
    the module, then it's __name__ attribute is "__main__". In this scenario, we obtain the module's filename.

    The returned string is as close to a unique Python name for the caller's defining module.

    NOTE: If :param:`fallback_name` is provided and is not-None and non-empty, then, in the event that
          the logger name cannot be inferred from the calling __main__ module, this value will be used
          instead of raising a ValueError.
    """
    # Get the module where the calling function is defined.
    # https://stackoverflow.com/questions/1095543/get-name-of-calling-functions-module-in-python
    stack = inspect.stack()
    calling_frame = stack[1]
    calling_module = inspect.getmodule(calling_frame[0])
    if calling_module is None:
        raise ValueError(
            f"Cannot obtain module from calling function. Tried to use calling frame {calling_frame}"
        )
    # we try to use this module's name
    name = calling_module.__name__
    if name == "__main__":
        # unless logger_name was called from an executing script,
        # in which case we use it's file name

        if hasattr(calling_module, "__file__"):
            return filename_wo_ext(calling_module.__file__)
        if fallback_name is not None:
            fallback_name = fallback_name.strip()
            if len(fallback_name) > 0:
                return fallback_name
        raise ValueError("Cannot determine calling module's name from its __file__ attribute!")
    return name


class TqdmLoggingHandler(logging.Handler):
    def __init__(self, level=logging.NOTSET) -> None:
        super().__init__(level)

    def emit(self, record) -> None:
        try:
            msg = self.format(record)
            tqdm.tqdm.write(msg)
            self.flush()
        except (KeyboardInterrupt, SystemExit):
            raise
        except:  # noqa: E722
            self.handleError(record)


def print_logger() -> logging.Logger:
    """A logger that is a facade over writing to STDOUT. Has no formatting."""
    logger = logging.getLogger("print-logger")
    logger.setLevel(logging.DEBUG)
    logging.basicConfig(
        stream=sys.stdout,
        format="%(message)s",
    )
    return logger


def deprecation_warning(logger: logging.Logger, msg: str) -> None:
    """Creates a deprecation warning log event with given the message and logger."""
    logger.warning(msg)
    warnings.simplefilter("always", DeprecationWarning)
    warnings.warn(msg, DeprecationWarning)


def silence_chatty_logger(*logger_names, quieter=logging.FATAL) -> None:
    """Sets loggers to the `quieter` level, which defaults to the highest (FATAL).

    Accepts a variable number of logger names.
    """
    for name in logger_names:
        log = logging.getLogger(name)
        log.setLevel(quieter)


def silence_chatty_datadog_loggers(*, silence_internal_writer: bool = False) -> None:
    """Drastically reduces the log activity of the Datadog trace reporting logger.

    NOTE: Traces still occur. The following useless logs in this format are not written anymore:

        trace XYZXYASGT sampled (1/1 spans sampled), KK additional messages skipped

    This specifically sets the `dtrace.internal.processor.trace` logger to FATAL.

    If `silence_internal_writer` is True, then the `ddtrace.internal.writer` is also set to FATAL.
    This silences logs of the form:

        ERROR:ddtrace.internal.writer:failed to send traces to Datadog Agent at http://localhost:8126

    """
    silence_chatty_logger("dtrace.internal.processor.trace", quieter=logging.FATAL)
    if silence_internal_writer:
        silence_chatty_logger("ddtrace.internal.writer", quieter=logging.FATAL)


@contextmanager
def loggers_at_level(*loggers_or_names, new_level: int) -> None:
    """Temporarily set one or more loggers to a specific level, resetting to previous levels on context end.

    :param:`loggers_or_names` is one or more :class:`logging.Logger` instances, or `str` names
                              of loggers regiested via `logging.getLogger`.
    :param:`new_level` is the new logging level to set during the context.
                       See `logging.{DEBUG,INFO,WARNING,ERROR,FATAL}` for values & documentation.

    To illustrate use, see this pseudocode example:
    >>>> import logging
    >>>> from llm_engine_server.core.loggers import loggers_at_level, make_logger
    >>>>
    >>>> your_logger = make_logger('your_logger')
    >>>>
    >>>> with loggers_at_level(
    >>>>   your_logger,
    >>>>   'llm_engine_server.core.loggers',
    >>>>   'document_core.utils.k8s',
    >>>>   new_level=logging.FATAL,
    >>>> ):
    >>>>   # do_something_while_those_loggers_will_only_log_FATAL_messages
    >>>>   your_logger.info("this will not be logged")
    >>>>   logging.getLogger('llm_engine_server.core.loggers').warning("neither will this")
    >>>>
    >>>> your_logger.info("this will be logged")
    """
    loggers: Sequence[logging.Logger] = [
        (logging.getLogger(log) if isinstance(log, str) else log) for log in loggers_or_names
    ]
    previous_levels: Sequence[int] = [log.level for log in loggers]
    try:
        for log in loggers:
            log.setLevel(new_level)

        yield

    finally:
        for log, level in zip(loggers, previous_levels):
            log.setLevel(level)


def filename_wo_ext(filename: str) -> str:
    """Gets the filename, without the file extension, if present."""
    return os.path.split(filename)[1].split(".", 1)[0]
