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
    """Renders file size downloaded and total, e.g. '0.5/2.3 GB'.

    Args:
        binary_units (bool, optional): Use binary units, KiB, MiB etc. Defaults to False.
    """

    def __init__(
        self, binary_units: bool = False, table_column: Optional[rich.table.Column] = None
    ) -> None:
        self.binary_units = binary_units
        super().__init__(table_column=table_column)

    def render(self, task: rich.progress.Task) -> rich.text.Text:
        speed = task.finished_speed or task.speed
        if speed is None:
            return rich.text.Text("- fps", style="green")
        return rich.text.Text(f"{speed:.1f} fps", style="green")


class ProgressNotifier(object):

    _DURATION_RX = re.compile(rb"Duration: (\d{2}):(\d{2}):(\d{2})\.\d{2}")
    _PROGRESS_RX = re.compile(rb"time=(\d{2}):(\d{2}):(\d{2})\.\d{2}")
    _DEST_RX = re.compile(rb"to '(.*)':")
    _FPS_RX = re.compile(rb"(\d{2}\.\d{2}|\d{2}) fps")

    @staticmethod
    def _seconds(hours, minutes, seconds):
        return (int(hours) * 60 + int(minutes)) * 60 + int(seconds)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        if self.pbar is not None:
            self.pbar.stop()

    def __init__(self, file=None, encoding=None, console = rich.console.Console(stderr=True)):
        self.lines = []
        self.line_acc = bytearray()
        self.duration = None
        self.dest = None
        self.started = False
        self.pbar = None
        self.pbar_task = None
        self.fps = None
        self.file = file or sys.stderr
        self.encoding = encoding or locale.getpreferredencoding() or 'UTF-8'
        self.console = console

    def __call__(self, char, stdin = None):
        if isinstance(char, str):
            char = char.encode('ascii')
        if char in b"\r\n":
            line = self.newline()
            if self.duration is None:
                self.duration = self.get_duration(line)
            if self.dest is None:
                self.dest = self.get_dest(line)
            if self.fps is None:
                self.fps = self.get_fps(line)
            self.progress(line)
        else:
            self.line_acc.extend(char)
            if self.line_acc[-6:] == bytearray(b"[y/N] "):
                print(self.line_acc.decode(self.encoding), end="", file=self.file)
                self.file.flush()
                if stdin:
                    stdin.put(input() + "\n")
                self.newline()

    def newline(self):
        line = bytes(self.line_acc)
        self.lines.append(line)
        self.line_acc = bytearray()
        return line

    def get_fps(self, line):
        search = self._FPS_RX.search(line)
        if search is not None:
            return round(float(search.group(1)))
        return None

    def get_duration(self, line):
        search = self._DURATION_RX.search(line)
        if search is not None:
            return self._seconds(*search.groups())
        return None

    def get_dest(self, line):
        search = self._DEST_RX.search(line)
        if search is not None:
            return os.path.basename(search.group(1).decode(self.encoding))
        return None

    def progress(self, line):
        search = self._PROGRESS_RX.search(line)
        if search is not None:

            total = self.duration
            current = self._seconds(*search.groups())
            unit = " seconds"

            if self.fps is not None:
                unit = " frames"
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
                    console=self.console
                )
                self.pbar_task = self.pbar.add_task(description=self.dest, total=total)
                self.pbar.start()

            self.pbar.update(self.pbar_task, completed=current)

def main(argv=None, stream=sys.stderr, encoding=None, console=rich.console.Console(stderr=True)):
    argv = argv or sys.argv[1:]
    console = rich.console.Console(file=stream)

    try:
        with ProgressNotifier(file=stream, encoding=encoding, console=console) as notifier:

            cmd = ["ffmpeg"] + argv
            p = subprocess.Popen(cmd, stderr=subprocess.PIPE)

            while True:
                out = p.stderr.read(1)
                if out == b"" and p.poll() != None:
                    break
                if out != b"":
                    notifier(out)

    except KeyboardInterrupt:
        console.print("Received KeyboardInterrupt, exiting...")
        return signal.SIGINT + 128  # POSIX standard

    except Exception as err:
        console.print("Unexpected exception:", err)
        return 1

    else:
        if p.returncode != 0:
            print(notifier.lines[-1].decode(notifier.encoding), file=stream)
        return p.returncode


if __name__ == "__main__":
    sys.exit(main())
