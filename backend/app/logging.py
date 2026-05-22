import structlog


def configure_logging() -> None:
    import logging

    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.dev.ConsoleRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(
            logging.getLevelName("DEBUG")
        ),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(),
    )
