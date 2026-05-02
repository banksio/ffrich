#!/usr/bin/env python
# coding: utf-8

# Copyright (c) 2017-2021 Martin Larralde <martin.larralde@ens-paris-saclay.fr>
# Copyright (c) 2022-2026 Nathan Banks
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in all
# copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND,
# EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF
# MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT.
# IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM,
# DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR
# OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE
# OR OTHER DEALINGS IN THE SOFTWARE.

"""A progress bar for `ffmpeg` using `rich`.
"""

import locale
import os
import re
import signal
import sys
import subprocess
from typing import Optional

import rich.console
import rich.progress
import rich.table
import rich.text


class FramesPerSecondColumn(rich.progress.ProgressColumn):
    """Render the current ffmpeg frame rate in a rich progress bar."""

    def __init__(
        self,
        binary_units: bool = False,
        table_column: Optional[rich.table.Column] = None,
    ) -> None:
        """Initialize the FPS column.

        Args:
            binary_units: Use binary units for sizing, if supported.
            table_column: Optional parent table column for rich.
        """
        self.binary_units = binary_units
        super().__init__(table_column=table_column)

    def render(self, task: rich.progress.Task) -> rich.text.Text:
        """Render a formatted frames-per-second value."""
        speed = task.finished_speed or task.speed
        if speed is None:
            return rich.text.Text("- fps", style="green")
        return rich.text.Text(f"{speed:.1f} fps", style="green")


class ProgressNotifier(object):
    """Track ffmpeg progress output and render a rich progress bar."""

    _DURATION_RX = re.compile(rb"Duration: (\d{2}):(\d{2}):(\d{2})\.\d{2}")
    _PROGRESS_RX = re.compile(rb"time=(\d{2}):(\d{2}):(\d{2})\.\d{2}")
    _DEST_RX = re.compile(rb"to '(.*)':")
    _FPS_RX = re.compile(rb"(\d{2}\.\d{2}|\d{2}) fps")

    @staticmethod
    def _seconds(hours, minutes, seconds):
        """Convert an hours/minutes/seconds tuple into total seconds."""
        return (int(hours) * 60 + int(minutes)) * 60 + int(seconds)

    def __enter__(self):
        """Enter the progress notifier context."""
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        """Stop the progress bar when exiting the context."""
        if self.pbar is not None:
            self.pbar.stop()

    def __init__(
        self,
        file=None,
        encoding=None,
        console: Optional[rich.console.Console] = None,
    ):
        """Initialize a new ProgressNotifier.

        Args:
            file: Stream to print prompts and ffmpeg output to.
            encoding: Encoding used to decode ffmpeg output.
            console: Rich console used for progress rendering.
        """
        self.line_acc = bytearray()
        self.duration = None
        self.dest = None
        self.started = False
        self.pbar = None
        self.pbar_task = None
        self.fps = None
        self.file = file or sys.stderr
        self.encoding = encoding or locale.getpreferredencoding() or 'UTF-8'
        self.console = console or rich.console.Console(stderr=True)

    def __call__(self, chunk: bytes, stdin=None):
        """Process ffmpeg output chunks."""
        for i in range(len(chunk)):
            char = chunk[i]
            if char in b"\r\n":
                line = self.newline()
                if self.duration is None:
                    self.duration = self.get_duration(line)
                if self.dest is None:
                    self.dest = self.get_dest(line)
                if self.fps is None:
                    self.fps = self.get_fps(line)
                if not self.progress(line):
                    self.print_log(line)
            else:
                self.line_acc.append(char)
                if self.line_acc[-6:] == bytearray(b"[y/N] "):
                    line = self.line_acc.decode(self.encoding, errors="replace")
                    self.console.print(rich.text.Text.from_ansi(line), end="")
                    self.console.file.flush()
                    if stdin:
                        stdin.put(input() + "\n")
                    self.newline()

    def print_log(self, line: bytes, end="\n"):
        """Print a log line to the console, preserving ANSI colors."""
        decoded = line.decode(self.encoding, errors="replace")
        self.console.print(rich.text.Text.from_ansi(decoded), end=end, soft_wrap=True)

    def newline(self):
        """Finalize the current line of ffmpeg output."""
        line = bytes(self.line_acc)
        self.line_acc = bytearray()
        return line

    def get_fps(self, line):
        """Parse the current frame rate from an ffmpeg output line."""
        search = self._FPS_RX.search(line)
        if search is not None:
            return round(float(search.group(1)))
        return None

    def get_duration(self, line):
        """Parse the total duration from an ffmpeg output line."""
        search = self._DURATION_RX.search(line)
        if search is not None:
            return self._seconds(*search.groups())
        return None

    def get_dest(self, line):
        """Parse the destination filename from an ffmpeg output line."""
        search = self._DEST_RX.search(line)
        if search is not None:
            return os.path.basename(search.group(1).decode(self.encoding))
        return None

    def progress(self, line):
        """Update the progress bar using the latest ffmpeg time output."""
        search = self._PROGRESS_RX.search(line)
        if search is not None:
            total = self.duration
            current = self._seconds(*search.groups())

            if self.fps is not None:
                current *= self.fps
                if total:
                    total *= self.fps

            if self.pbar is None:
                self.pbar = rich.progress.Progress(
                    rich.progress.SpinnerColumn(),
                    rich.progress.TextColumn("[progress.description]{task.description}"),
                    rich.progress.BarColumn(),
                    rich.progress.TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
                    rich.progress.TextColumn("{task.completed}/{task.total}"),
                    FramesPerSecondColumn(),
                    rich.progress.TimeRemainingColumn(),
                    console=self.console,
                )
                self.pbar_task = self.pbar.add_task(
                    description=self.dest or "",
                    total=total,
                )
                self.pbar.start()

            pbar_task = self.pbar_task
            assert pbar_task is not None
            self.pbar.update(pbar_task, completed=current)
            return True
        return False

    def flush(self):
        """Finalize and print any remaining output."""
        if self.line_acc:
            line = self.newline()
            if not self.progress(line):
                self.print_log(line, end="")


def main(
    argv=None,
    stream=sys.stderr,
    encoding=None,
    console: Optional[rich.console.Console] = None,
):
    """Run ffmpeg with a rich progress bar for stderr output."""
    argv = argv or sys.argv[1:]
    console = console or rich.console.Console(file=stream, force_terminal=True)

    try:
        with ProgressNotifier(
            file=stream,
            encoding=encoding,
            console=console,
        ) as notifier:
            cmd = ["ffmpeg"] + argv
            env = os.environ.copy()
            env["AV_LOG_FORCE_COLOR"] = "1"
            p = subprocess.Popen(cmd, stderr=subprocess.PIPE, env=env)
            stderr = p.stderr
            if stderr is None:
                raise RuntimeError("ffmpeg stderr pipe is unavailable")

            while True:
                chunk = stderr.read1(1024)
                if not chunk and p.poll() is not None:
                    break
                if chunk:
                    notifier(chunk)
            notifier.flush()

    except KeyboardInterrupt:
        console.print("Received KeyboardInterrupt, exiting...")
        return signal.SIGINT + 128  # POSIX standard

    except Exception as err:
        console.print("Unexpected exception:", err)
        return 1

    else:
        return p.returncode



if __name__ == "__main__":
    sys.exit(main())
