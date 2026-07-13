# Upload Assistant © 2025 Audionut & wastaken7 — Licensed under UAPL v1.0
from typing import Any


class LoginError(Exception):
    def __init__(self, *args: Any, **kwargs: Any) -> None:
        default_message = "An error occurred while logging in"
        # if any arguments are passed...
        # If you inherit from the exception that takes message as a keyword
        # maybe you will need to check kwargs here
        if args:
            # ... pass them to the super constructor
            super().__init__(*args, **kwargs)
        else:  # else, the exception was raised without arguments ...
            # ... pass the default message to the super constructor
            super().__init__(default_message, **kwargs)


class UploadError(Exception):
    def __init__(self, *args: Any, **kwargs: Any) -> None:
        default_message = "An error occurred while uploading"
        # if any arguments are passed...
        # If you inherit from the exception that takes message as a keyword
        # maybe you will need to check kwargs here
        if args:
            # ... pass them to the super constructor
            super().__init__(*args, **kwargs)
        else:  # else, the exception was raised without arguments ...
            # ... pass the default message to the super constructor
            super().__init__(default_message, **kwargs)


class XEMNotFoundError(Exception):
    pass


class WeirdSystemError(Exception):
    pass


class ManualDateError(Exception):
    pass


class NoAudioMediaError(Exception):
    pass
