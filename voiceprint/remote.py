"""Talking to the Modal deployment in the user's own workspace."""

from __future__ import annotations

import subprocess
import sys

import modal

from voiceprint.modal_app import APP_NAME

DEPLOY_HINT = (
    "voiceprint isn't deployed to your Modal workspace yet.\n"
    "Run:  modal token new   (once, if you haven't)\n"
    "      voiceprint deploy"
)


class NotDeployed(Exception):
    pass


def deploy() -> int:
    """`modal deploy` the app. Deployed once, then containers stay warm between
    CLI calls — an ephemeral app would cold-start the base model every time."""
    return subprocess.call(
        [sys.executable, "-m", "modal", "deploy", "-m", "voiceprint.modal_app"]
    )


def _lookup(fn):
    try:
        return fn()
    except modal.exception.NotFoundError as error:
        raise NotDeployed(DEPLOY_HINT) from error


def trainer():
    return _lookup(lambda: modal.Function.from_name(APP_NAME, "train_voice"))


def writer(model: str):
    return _lookup(lambda: modal.Cls.from_name(APP_NAME, "Writer"))(model=model)
