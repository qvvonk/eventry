from eventry.config import HandlerManagerConfig, FromKwargs


handler_manager_config = HandlerManagerConfig(
    positional_only_args=(FromKwargs('Event'), )
)