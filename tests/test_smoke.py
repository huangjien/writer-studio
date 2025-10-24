def test_import_and_logging():
    from writer_studio.logging import get_logger, init_logging

    # Initialize logging and get a logger
    init_logging("DEBUG")
    log = get_logger("test")
    log.debug("smoke test debug message")

    assert callable(init_logging)
    assert hasattr(log, "debug")
