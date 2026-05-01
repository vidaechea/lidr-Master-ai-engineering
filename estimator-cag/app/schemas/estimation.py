from enum import Enum


class ExampleFormat(str, Enum):
    MARKDOWN = "markdown"
    JSON = "json"
    NARRATIVE = "narrative"
