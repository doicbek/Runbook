class InputUnavailableError(Exception):
    """Raised when an agent cannot acquire the data/inputs needed for its task.

    This triggers the automatic input-acquisition workflow: the executor inserts
    a prerequisite sub-action that researches how to obtain the data and
    downloads it, then retries the original task with the new artifacts.
    """

    def __init__(self, message: str, tried: list[str] | None = None):
        super().__init__(message)
        self.tried = tried or []
