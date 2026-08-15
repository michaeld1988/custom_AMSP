"""
Minimal Siril stand-in for the tests.

sirilpy only exists inside Siril, so the tests install this package under the
name 'sirilpy' before importing Custom_AMSP.  FakeSiril records every command
and creates the files a real Siril would create, which is enough for the
engine's existence checks (sequence files, master files, saved stacks).
"""

import sys
import types
from pathlib import Path


class LogColor:
    GREEN = 'green'
    BLUE = 'blue'
    SALMON = 'salmon'
    RED = 'red'


class SirilError(Exception):
    pass


class CommandError(SirilError):
    pass


class DataError(SirilError):
    pass


class SirilConnectionError(SirilError):
    pass


def _unquote(tok: str) -> str:
    return tok.strip().strip('"')


class FakeSiril:
    """Records commands; fabricates the outputs the engine looks for."""

    def __init__(self, wd: Path | None = None):
        # SirilInterface() is constructed without arguments by the UI
        self.wd = Path(wd) if wd is not None else Path.cwd()
        self.cwd = self.wd
        self.commands: list[list[str]] = []
        self.logs: list[str] = []
        # Commands issued from a directory that does not hold their sequence.
        # Real Siril would fail; the tests assert this stays empty.
        self.violations: list[str] = []

    # ── SirilInterface API used by the engine ────────────────────────────────

    def connect(self):
        return True

    def get_siril_wd(self) -> str:
        return str(self.wd)

    def log(self, msg, color=None):
        self.logs.append(str(msg))

    def cmd(self, *args):
        tokens = [str(a) for a in args]
        # 'cd /some/path' arrives as a single token, everything else is split
        if len(tokens) == 1 and ' ' in tokens[0]:
            head, _, rest = tokens[0].partition(' ')
            tokens = [head, rest]
        self.commands.append(tokens)
        name = tokens[0]
        rest = tokens[1:]
        handler = getattr(self, f'_do_{name}', None)
        if handler:
            handler(rest)

    # ── Command emulation ────────────────────────────────────────────────────

    def _touch(self, path: Path):
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        if not path.exists():
            path.write_bytes(b'FAKE')

    def _out_path(self, rest: list[str]) -> Path | None:
        for tok in rest:
            tok = _unquote(tok)
            if tok.startswith('-out='):
                return Path(tok[len('-out='):])
        return None

    def _do_cd(self, rest):
        self.cwd = Path(_unquote(rest[0]))
        self.cwd.mkdir(parents=True, exist_ok=True)

    def _do_convert(self, rest):
        self._touch(self.cwd / f'{rest[0]}.seq')

    def _require_seq(self, name: str, seq: str):
        if not (self.cwd / f'{seq}.seq').exists():
            self.violations.append(f'{name} {seq}: no {seq}.seq in {self.cwd}')

    def _do_calibrate(self, rest):
        self._require_seq('calibrate', rest[0])
        self._touch(self.cwd / f'pp_{rest[0]}.seq')

    def _do_seqsubsky(self, rest):
        self._touch(self.cwd / f'bkg_{rest[0]}.seq')

    def _do_stack(self, rest):
        self._require_seq('stack', rest[0])
        out = self._out_path(rest)
        if out is not None:
            self._touch(out.with_name(out.name + '.fit'))

    def _do_register(self, rest):
        self._touch(self.cwd / f'r_{rest[0]}.seq')

    def _do_seqapplyreg(self, rest):
        self._touch(self.cwd / f'r_{rest[0]}.seq')

    def _do_merge(self, rest):
        self._touch(self.cwd / f'{_unquote(rest[-1])}.seq')

    def _do_save(self, rest):
        # The real Siril expands the keyword pattern; the engine only needs
        # *a* new FITS file to appear in the current directory.
        n = sum(1 for c in self.commands if c and c[0] == 'save')
        self._touch(self.cwd / f'saved_{n:03d}.fit')

    def _do_load(self, rest):
        pass

    # ── Convenience for assertions ───────────────────────────────────────────

    def calibrate_calls(self) -> list[list[str]]:
        return [c for c in self.commands if c and c[0] == 'calibrate']

    def stack_calls(self) -> list[list[str]]:
        return [c for c in self.commands if c and c[0] == 'stack']


def install_stub_sirilpy():
    """Register a fake 'sirilpy' module so Custom_AMSP can be imported."""
    mod = types.ModuleType('sirilpy')
    mod.LogColor = LogColor
    mod.SirilError = SirilError
    mod.CommandError = CommandError
    mod.DataError = DataError
    mod.SirilConnectionError = SirilConnectionError
    mod.SirilInterface = FakeSiril
    mod.ensure_installed = lambda *a, **kw: None
    sys.modules['sirilpy'] = mod
    return mod
