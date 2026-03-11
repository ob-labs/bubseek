"""Bub plugin entry for Marimo channel."""

from bub import hookimpl
from bub.channels import Channel
from bub.types import MessageHandler

from .channel import MarimoChannel


@hookimpl
def provide_channels(message_handler: MessageHandler) -> list[Channel]:
    return [MarimoChannel(message_handler)]
