"""Bub plugin entry for DingTalk channel."""

from bub import hookimpl
from bub.channels import Channel
from bub.types import MessageHandler


@hookimpl
def provide_channels(message_handler: MessageHandler) -> list[Channel]:
    from .channel import DingTalkChannel

    return [DingTalkChannel(message_handler)]
