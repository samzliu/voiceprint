"""Everything that talks to Modal.

This is the only module in the package that imports `modal`. Everything else
works in terms of voices, chunks and drafts, and asks this module when it needs
something to happen in the cloud. Keeping the boundary here is what lets the
rest of the code be tested without an account, and what makes it obvious exactly
what this tool does inside someone else's infrastructure.
"""

from __future__ import annotations

import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

import modal

from voiceprint.modal_app import APP_NAME, CACHE_VOLUME, VOICES_VOLUME

DEPLOY_HINT = (
    "voiceprint isn't deployed to your Modal workspace yet.\n"
    "Run:  modal token new   (once, if you haven't)\n"
    "      voiceprint deploy"
)


class NotDeployed(Exception):
    pass


@dataclass
class Stored:
    adapters: list[tuple[str, int]]
    cache_bytes: int

    @property
    def adapter_bytes(self) -> int:
        return sum(size for _name, size in self.adapters)


def is_authenticated() -> bool:
    return (Path.home() / ".modal.toml").exists() or bool(
        __import__("os").environ.get("MODAL_TOKEN_ID")
    )


def deploy() -> int:
    """`modal deploy` the app. Deployed once, then containers stay warm between
    CLI calls — an ephemeral app would cold-start the base model every time."""
    return _modal("deploy", "-m", "voiceprint.modal_app")


def stop() -> int:
    """Shut down warm containers now instead of waiting out the idle window."""
    return _modal("app", "stop", APP_NAME, "--yes")


def uninstall(drop_cache: bool) -> list[str]:
    """Remove voiceprint from the user's Modal account.

    Anyone who installs a tool into their own cloud account deserves a clean way
    to take it back out, including the tens of gigabytes of model weights it
    quietly parked in a volume.
    """
    done = []
    _modal("app", "stop", APP_NAME, "--yes")
    done.append(f"stopped and undeployed the '{APP_NAME}' app")
    if drop_cache:
        _modal("volume", "delete", CACHE_VOLUME, "--yes")
        done.append(f"deleted the '{CACHE_VOLUME}' volume (cached model weights)")
        _modal("volume", "delete", VOICES_VOLUME, "--yes")
        done.append(f"deleted the '{VOICES_VOLUME}' volume (your adapters)")
    return done


def stored() -> Stored:
    """What voiceprint is keeping in the user's account, and how big it is."""
    adapters = []
    for entry in _volume(VOICES_VOLUME).listdir("/"):
        size = sum(
            f.size
            for f in _volume(VOICES_VOLUME).listdir(f"/{entry.path}", recursive=True)
            if f.type == modal.volume.FileEntryType.FILE
        )
        adapters.append((entry.path, size))

    cache = sum(
        f.size
        for f in _volume(CACHE_VOLUME).listdir("/", recursive=True)
        if f.type == modal.volume.FileEntryType.FILE
    )
    return Stored(adapters=sorted(adapters), cache_bytes=cache)


def delete_adapter(name: str) -> bool:
    try:
        _volume(VOICES_VOLUME).remove_file(f"/{name}", recursive=True)
    except (FileNotFoundError, modal.exception.NotFoundError):
        return False
    return True


def trainer():
    return _lookup(lambda: modal.Function.from_name(APP_NAME, "train_voice"))


def writer(model: str):
    return _lookup(lambda: modal.Cls.from_name(APP_NAME, "Writer"))(model=model)


def job_result(job_id: str) -> dict | None:
    """The training job's result, or None while it is still running."""
    try:
        return modal.FunctionCall.from_id(job_id).get(timeout=0)
    except TimeoutError:
        return None


def is_deployed() -> bool:
    try:
        trainer()
        return True
    except NotDeployed:
        return False


def _volume(name: str):
    return modal.Volume.from_name(name, create_if_missing=True)


def _lookup(fn):
    try:
        return fn()
    except modal.exception.NotFoundError as error:
        raise NotDeployed(DEPLOY_HINT) from error


def _modal(*args: str) -> int:
    return subprocess.call([sys.executable, "-m", "modal", *args])
