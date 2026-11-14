"""Streaming reader for .echoreplay files (zip or plain text, one `<timestamp>\\t<json>` frame per line)."""

import heapq
import re
import struct
import zipfile
import zlib
from calendar import monthrange
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime, timedelta
from pathlib import Path

from .errors import CorruptReplay, IncompleteReplay, UnsupportedReplay
from .frames import build_frame, build_meta, split_raw
from .models import Frame, ReplayMeta

ZIP_MAGIC = b"PK\x03\x04"
SUPPORTED_MATCH_TYPE = "Echo_Combat"
MAX_UNCOMPRESSED_BYTES = 1024**3
BAD_LINE_ERRORS = (ValueError, KeyError, TypeError, IndexError)  # incl. JSON and UTF-8 decode errors


def _allowed_bad_lines(lines_read: int) -> int:
    return max(10, lines_read // 100)


def _limited(lines: Iterator[bytes], max_bytes: int) -> Iterator[bytes]:
    total = 0
    for line in lines:
        total += len(line)
        if total > max_bytes:
            raise CorruptReplay(f"Replay content exceeds {max_bytes // 1024**2} MB uncompressed")
        yield line


READ_CHUNK = 1024 * 1024  # few large reads: the replays live on a network share
META_CHUNK = 64 * 1024  # the metadata is in the first line only


def _chunk_lines(fh, chunk_size: int = READ_CHUNK) -> Iterator[bytes]:
    """Same lines as iterating the file (each ends with b"\n" except perhaps the last), read in big chunks."""
    pending: list[bytes] = []  # pieces of the unfinished line (a list: a very long line is not copied per chunk)
    while chunk := fh.read(chunk_size):
        end = chunk.rfind(b"\n") + 1
        if not end:
            pending.append(chunk)
            continue
        pending.append(chunk[:end])
        lines = b"".join(pending).split(b"\n")
        lines.pop()  # empty piece after the last newline
        for line in lines:
            yield line + b"\n"
        pending = [chunk[end:]] if end < len(chunk) else []
    if pending:
        yield b"".join(pending)


LOCAL_HEADER = struct.Struct("<4sHHHHHIIIHH")  # zip local file header (30 bytes)
SALVAGE_CHUNK = 1024 * 1024


def _salvage_zip_lines(path: Path, max_bytes: int, notes: list[str]) -> Iterator[bytes]:
    """Repair mode (D36): read the first .echoreplay entry straight from its local header and inflate
    until the data ends or breaks; ignores the central directory and CRC, so a truncated or partly
    damaged zip still yields everything before the damage."""
    data = path.read_bytes()
    pos = data.find(ZIP_MAGIC)
    while pos != -1:
        fields = LOCAL_HEADER.unpack_from(data, pos) if pos + LOCAL_HEADER.size <= len(data) else None
        if fields:
            method, name_len, extra_len = fields[3], fields[9], fields[10]
            name = data[pos + 30 : pos + 30 + name_len].decode("utf-8", "replace")
            if name.lower().endswith(".echoreplay"):
                start = pos + 30 + name_len + extra_len
                break
        pos = data.find(ZIP_MAGIC, pos + 4)
    else:
        raise CorruptReplay("Repair: no .echoreplay entry found in the damaged zip")

    def chunks() -> Iterator[bytes]:
        if method == 0:  # stored
            yield data[start:]
            return
        inflater = zlib.decompressobj(-15)
        offset = start
        while offset < len(data):
            try:
                out = inflater.decompress(data[offset : offset + SALVAGE_CHUNK])
            except zlib.error:
                notes.append(f"zip data damaged after {(offset - start) // 1024:,} KB; later frames lost")
                return
            offset += SALVAGE_CHUNK
            if out:
                yield out
            if inflater.eof:
                return
        notes.append("zip data ends early (file truncated); later frames lost")

    def lines() -> Iterator[bytes]:
        pending = b""
        for chunk in chunks():
            pending += chunk
            *complete, pending = pending.split(b"\n")
            for line in complete:
                yield line + b"\n"
        if pending:
            yield pending

    return _limited(lines(), max_bytes)


# --- aggressive repair (D36b) ----------------------------------------------------------------------
# For replays that still fail after repair mode. On the share these are files hit by a crash / power cut on the
# recording PC: 4 KB disk blocks overwritten with zero bytes or with another file's data, zip headers gone. Recorded
# zips usually hold the frames twice (the .echoreplay entry and images/image.png, the same compressed bytes), so:
#   - entries are found from the central directory when local headers are wiped, and from local headers otherwise;
#   - where two copies differ, the bytes that decode into readable frames are used (the damage is rarely in the
#     same place in both);
#   - each stream is read up to its first damage that cannot be patched. Nothing after it is guessed: deflate output
#     there depends on the 32 KB before the damage (tested on real replays: nothing after a gap comes back right),
#     and zlib decodes zero bytes or foreign data without an error, into junk. So every decoded line is checked and
#     reading stops at the first one that is not a frame;
#   - frames of all streams are merged in time order, each kept once, only of this replay's session (a damaged disk
#     can put another match's data into the file).

CENTRAL_HEADER = struct.Struct("<4s6H3I5H2I")  # zip central directory record (46 bytes)
CENTRAL_MAGIC = b"PK\x01\x02"
FRAME_START = re.compile(rb"\d{4}[-/]\d{1,2}[-/]\d{1,2} \d{1,2}:\d{2}:\d{2}(?:\.\d+)?\t\{")
SESSION_IN_NAME = re.compile(r"[0-9A-Fa-f]{8}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{12}")
HOLE = re.compile(rb"\x00{64,}")  # never in deflate data or frame text: a wiped disk block
CHECK_CHUNK = 16 * 1024  # compressed bytes per step: on a decode error only this much output is lost
LOOKAHEAD = 64 * 1024  # compressed bytes decoded past a patched range to tell which copy is right
DIFF_UNIT = 64  # granularity of the comparison of two copies


def _zip_entries(data: bytes) -> list[tuple[int, int | None, int]]:
    """(data start, compressed size or None, method) of every entry still findable: from the central directory
    (works when the local headers are wiped) and from local headers (works when the directory is gone)."""
    found: dict[int, tuple[int, int | None, int]] = {}
    pos = data.find(CENTRAL_MAGIC)
    while pos != -1:
        if pos + CENTRAL_HEADER.size <= len(data):
            f = CENTRAL_HEADER.unpack_from(data, pos)
            method, csize, name_len, offset = f[4], f[8], f[10], f[16]
            local_extra = 0
            if data[offset : offset + 4] == ZIP_MAGIC and offset + LOCAL_HEADER.size <= len(data):
                local_extra = LOCAL_HEADER.unpack_from(data, offset)[10]
            start = offset + 30 + name_len + local_extra  # wiped local header: same name, no extra field
            if method in (0, 8) and start < len(data):
                found[start] = (start, csize or None, method)
        pos = data.find(CENTRAL_MAGIC, pos + 4)
    pos = data.find(ZIP_MAGIC)
    while pos != -1:
        if pos + LOCAL_HEADER.size <= len(data):
            f = LOCAL_HEADER.unpack_from(data, pos)
            method, csize, name_len, extra_len = f[3], f[7], f[9], f[10]
            start = pos + 30 + name_len + extra_len
            if method in (0, 8) and start < len(data) and start not in found:
                found[start] = (start, csize or None, method)
        pos = data.find(ZIP_MAGIC, pos + 4)
    return sorted(found.values())


def _same_copy(a: bytes, b: bytes) -> bool:
    """Two entries hold the same compressed bytes (apart from damage): most undamaged spots are equal."""
    if len(a) != len(b) or len(a) < 1024:
        return False
    equal = differ = 0
    for i in range(0, len(a) - 256, max(1, len(a) // 128)):
        x, y = a[i : i + 256], b[i : i + 256]
        if b"\x00\x00\x00\x00" in x or b"\x00\x00\x00\x00" in y:
            continue
        if x == y:
            equal += 1
        else:
            differ += 1
    return equal >= 4 and equal >= differ


def _differences(a: bytes, b: bytes) -> list[tuple[int, int]]:
    """Ranges where two copies differ, to DIFF_UNIT bytes (compared 4 KB at a time first: fast when equal)."""
    ranges: list[list[int]] = []
    for block in range(0, len(a), 4096):
        if a[block : block + 4096] == b[block : block + 4096]:
            continue
        for i in range(block, min(block + 4096, len(a)), DIFF_UNIT):
            if a[i : i + DIFF_UNIT] != b[i : i + DIFF_UNIT]:
                end = min(i + DIFF_UNIT, len(a))
                if ranges and ranges[-1][1] == i:
                    ranges[-1][1] = end
                else:
                    ranges.append([i, end])
    return [(s, e) for s, e in ranges]


def _is_frame(line: bytes) -> bool:
    if not FRAME_START.match(line):
        return False
    try:
        split_raw(line)
        return True
    except BAD_LINE_ERRORS:
        return False


class _CheckedInflate:
    """Raw deflate decoder that stops at the first decoded line that is not a frame (junk from damaged data) or at a
    hole; `out` holds the good output not taken yet. copy() gives an independent trial decoder."""

    def __init__(self, stored: bool = False):
        self.stored = stored
        self.inflater = None if stored else zlib.decompressobj(-15)
        self.tail = b""  # the line being decoded, not complete yet
        self.out: list[bytes] = []
        self.good_lines = 0
        self.dead = False
        self.eof = False

    def copy(self) -> "_CheckedInflate":
        other = _CheckedInflate.__new__(_CheckedInflate)
        other.__dict__ = dict(self.__dict__, out=[], good_lines=0)
        if self.inflater is not None:
            other.inflater = self.inflater.copy()
        return other

    def feed(self, data: bytes) -> bool:
        """False once damage is reached (and for good after that)."""
        hole = HOLE.search(data)
        if hole:
            data = data[: hole.start()]
        for i in range(0, len(data), CHECK_CHUNK):
            if self.dead or self.eof:
                break
            chunk = data[i : i + CHECK_CHUNK]
            if self.stored:
                decoded = chunk
            else:
                try:
                    decoded = self.inflater.decompress(chunk)
                except zlib.error:
                    self.dead = True
                    break
                self.eof = self.inflater.eof
            self._check(decoded)
        if hole and not self.eof:
            self.dead = True
        return not self.dead

    def _check(self, decoded: bytes) -> None:
        lines = (self.tail + decoded).split(b"\n")
        self.tail = lines.pop()
        good = []
        for line in lines:
            if line.strip() and not _is_frame(line):
                self.dead = True
                self.tail = b""
                break
            good.append(line + b"\n")
            self.good_lines += bool(line.strip())
        if good:
            self.out.append(b"".join(good))

    def take(self) -> bytes:
        taken = b"".join(self.out)
        self.out = []
        return taken

    def finish(self) -> bytes:
        """Output still pending; the last line only if the stream really ended (a cut line is junk)."""
        taken = self.take()
        if self.eof and not self.dead and _is_frame(self.tail):
            taken += self.tail
        return taken


def _read_one(body: bytes, stored: bool, label: str, notes: list[str]) -> Iterator[bytes]:
    state = _CheckedInflate(stored)
    for i in range(0, len(body), READ_CHUNK):
        state.feed(body[i : i + READ_CHUNK])
        yield state.take()
        if state.dead or state.eof:
            break
    yield state.finish()
    if state.dead:
        notes.append(f"{label}: damaged; frames after the damage lost")


def _read_two(a: bytes, b: bytes, stored: bool, label: str, notes: list[str]) -> Iterator[bytes]:
    """Two copies of one stream: where they differ, the copy whose bytes decode into frames is used."""
    ranges = _differences(a, b)
    state = _CheckedInflate(stored)
    pos = patched = 0
    for n, (start, end) in enumerate(ranges):
        state.feed(a[pos:start])
        yield state.take()
        if state.dead or state.eof:
            break
        next_start = ranges[n + 1][0] if n + 1 < len(ranges) else len(a)
        lookahead = a[end : min(next_start, end + LOOKAHEAD)]
        options = sorted((a[start:end], b[start:end]), key=lambda o: o.count(0))
        for option in options:
            trial = state.copy()
            if trial.feed(option) and trial.feed(lookahead) and (trial.good_lines or trial.eof or not lookahead):
                break
        else:
            option = options[0]  # neither copy is intact here: read up to the damage
        if option != a[start:end]:
            patched += end - start
        state.feed(option)
        yield state.take()
        pos = end
        if state.dead or state.eof:
            break
    else:
        state.feed(a[pos:])
    yield state.finish()
    if patched:
        notes.append(f"{label}: {patched // 1024:,} KB of damaged data taken from the zip's second copy")
    if state.dead:
        notes.append(f"{label}: damaged in both copies; frames after the damage lost")


def _streams(data: bytes, notes: list[str]) -> list[Iterator[bytes]]:
    """Decoded output of every zip entry; two copies of the same data are read as one."""
    entries = _zip_entries(data)
    if not entries:
        notes.append("no zip entry left in the file")
        return []
    if data[:4] != ZIP_MAGIC or data.find(CENTRAL_MAGIC) == -1:
        notes.append("zip headers damaged; entries found from what was left")
    bodies = [(data[start : start + size] if size else data[start:], method == 0) for start, size, method in entries]
    streams, used = [], set()
    for i, (a, stored) in enumerate(bodies):
        if i in used:
            continue
        twin = next((j for j in range(i + 1, len(bodies)) if j not in used and bodies[j][1] == stored
                     and _same_copy(a, bodies[j][0])), None)
        label = f"zip entry {len(streams) + 1}"
        if twin is None:
            streams.append(_read_one(a, stored, label, notes))
        else:
            used.add(twin)
            streams.append(_read_two(a, bodies[twin][0], stored, label, notes))
    return streams


def _frames(chunks: Iterator[bytes]) -> Iterator[tuple[datetime, str, bytes]]:
    """(timestamp, session id, line) of every frame; junk before a frame start (zero bytes, a cut line) is cut off,
    and two frames glued together by a lost newline are split again."""
    pending = b""
    for chunk in chunks:
        pending += chunk
        *complete, pending = pending.split(b"\n")
        for line in complete:
            yield from _frames_in(line)
    if pending:
        yield from _frames_in(pending)


def _frames_in(line: bytes) -> Iterator[tuple[datetime, str, bytes]]:
    starts = [m.start() for m in FRAME_START.finditer(line)]
    for a, b in zip(starts, starts[1:] + [len(line)]):
        piece = line[a:b].rstrip(b"\x00\r")
        try:
            timestamp, data = split_raw(piece)
        except BAD_LINE_ERRORS:
            continue
        yield timestamp, str(data.get("sessionid", "")).upper(), piece + b"\n"


def _merged(sources: list[Iterator[tuple[datetime, str, bytes]]], session: str | None) -> Iterator[bytes]:
    """Frames of all sources in time order, each once, of one session (the file name's, else the first frame's)."""
    last = None
    for timestamp, frame_session, line in heapq.merge(*sources, key=lambda t: t[0]):
        if session is None:
            session = frame_session
        if frame_session != session or (last is not None and timestamp <= last):
            continue
        last = timestamp
        yield line


def _aggressive_lines(path: Path, max_bytes: int, notes: list[str]) -> tuple[str, Iterator[bytes]]:
    """(container, frame lines) in aggressive repair mode."""
    data = path.read_bytes()
    plain = data[:4] != ZIP_MAGIC and data.find(CENTRAL_MAGIC) == -1 and FRAME_START.search(data, 0, 4 * 1024**2)
    if plain:  # text with junk in it: zero bytes, glued or cut lines
        sources = [_frames(iter([data]))]
    else:
        sources = [_frames(stream) for stream in _streams(data, notes)]
    named = SESSION_IN_NAME.search(path.name)
    session = named.group(0).upper() if named else None
    return ("plain" if plain else "zip"), _limited(_merged(sources, session), max_bytes)


@contextmanager
def _open_lines(path: Path, max_bytes: int, repair: bool | str = False, notes: list[str] | None = None,
                chunk_size: int = READ_CHUNK):
    """Yield (container, iterator of raw byte lines)."""
    if repair == "aggressive":
        yield _aggressive_lines(path, max_bytes, notes if notes is not None else [])
        return
    with path.open("rb") as fh:
        is_zip = fh.read(4) == ZIP_MAGIC
    if not is_zip:
        with path.open("rb", buffering=0) as fh:
            yield "plain", _limited(_chunk_lines(fh, chunk_size), max_bytes)
        return
    if repair:
        yield "zip", _salvage_zip_lines(path, max_bytes, notes if notes is not None else [])
        return
    try:
        with zipfile.ZipFile(path) as zf:
            # Recorded zips also contain images/image.png (a copy of the frames); use the first .echoreplay only.
            entry = next((i for i in zf.infolist() if i.filename.lower().endswith(".echoreplay")), None)
            if entry is None:
                raise CorruptReplay("Zip contains no .echoreplay entry")
            if entry.file_size > max_bytes:
                raise CorruptReplay(f"Replay content exceeds {max_bytes // 1024**2} MB uncompressed")
            with zf.open(entry) as fh:
                yield "zip", _limited(_chunk_lines(fh, chunk_size), max_bytes)
    except (zipfile.BadZipFile, zlib.error, EOFError) as e:
        raise CorruptReplay(f"Damaged zip file: {e}") from e


class ClockJumps:
    """The recorder stamps frames with the PC's wall-clock time (UK: GMT / BST), so a daylight-saving change in the
    middle of a match adds or removes an hour between two frames (a 7-minute match read as 67). Only a step that is
    one of the two UK changes is taken out, so every later frame keeps the clock the match started on:
      - last Sunday of March: 01:00 GMT -> 02:00 BST, a step of +1 hour right after a frame stamped 00:xx;
      - last Sunday of October: 02:00 BST -> 01:00 GMT, a step of -1 hour right after a frame stamped 01:xx.
    The step must be an hour within two minutes (frames come every fraction of a second). Any other jump is real."""

    STEP_S = 3600
    TOLERANCE_S = 120
    # month -> (sign of the step, hour of the last frame before it)
    CHANGES = {3: (1, 0), 10: (-1, 1)}

    def __init__(self):
        self.shift = timedelta(0)
        self.shifts: list[int] = []  # seconds, in the order they happened
        self._last: datetime | None = None

    def add(self, raw: datetime) -> None:
        """Look at the next frame's own (uncorrected) timestamp."""
        before = self._last
        self._last = raw
        if before is None or before.month not in self.CHANGES:
            return
        sign, hour = self.CHANGES[before.month]
        gap = (raw - before).total_seconds()
        last_sunday = before.weekday() == 6 and before.day + 7 > monthrange(before.year, before.month)[1]
        if last_sunday and before.hour == hour and abs(gap - sign * self.STEP_S) <= self.TOLERANCE_S:
            self.shift += timedelta(seconds=sign * self.STEP_S)
            self.shifts.append(sign * self.STEP_S)

    def fix(self, raw: datetime) -> datetime:
        return raw - self.shift

    def describe(self) -> str:
        return " and ".join(f"{s / 3600:+g} h" for s in self.shifts)


class ParsedReplay:
    """Metadata is read on construction; frames() streams the file again from the start."""

    def __init__(self, path: Path, max_uncompressed_bytes: int = MAX_UNCOMPRESSED_BYTES, repair: bool | str = False):
        """repair=True (D36): salvage mode for damaged files — damaged zips are read up to the damage,
        unreadable lines (including the first) are skipped without limit. repair="aggressive" (D36b): also rebuilds
        wiped zip headers, fills damage from the zip's second copy and reads on past damaged regions."""
        self.path = Path(path)
        self.max_bytes = max_uncompressed_bytes
        self.repair = repair
        self.warnings: list[str] = []
        self.frame_count = 0
        self.meta = self._read_meta()

    def _read_meta(self) -> ReplayMeta:
        skipped = 0
        with _open_lines(self.path, self.max_bytes, self.repair, chunk_size=META_CHUNK) as (container, lines):
            for raw in lines:
                if not raw.strip():
                    continue
                try:
                    timestamp, data = split_raw(raw)
                    meta = build_meta(timestamp, data, container)
                    break
                except BAD_LINE_ERRORS:
                    if not self.repair:
                        raise CorruptReplay("First frame is unreadable") from None
                    skipped += 1
            else:
                raise IncompleteReplay("Replay contains no readable frames" if self.repair else "Replay contains no frames")
        if meta.match_type != SUPPORTED_MATCH_TYPE:
            raise UnsupportedReplay(f"Only Echo Combat replays are supported (this is {meta.match_type or 'unknown'})")
        return meta

    def frames(self) -> Iterator[Frame]:
        self.warnings.clear()
        bad_lines = lines_read = index = 0
        last_line_bad = False
        notes: list[str] = []
        clock = ClockJumps()
        with _open_lines(self.path, self.max_bytes, self.repair, notes) as (_, lines):
            for raw in lines:
                lines_read += 1
                if not raw.strip():
                    continue
                if last_line_bad:  # the bad line was not the last one
                    bad_lines += 1
                    last_line_bad = False
                    if not self.repair and bad_lines > _allowed_bad_lines(lines_read):
                        raise CorruptReplay(f"Too many unreadable lines ({bad_lines} of {lines_read})")
                try:
                    timestamp, data = split_raw(raw)
                    clock.add(timestamp)
                    frame = build_frame(index, clock.fix(timestamp), data)
                except BAD_LINE_ERRORS:
                    last_line_bad = True
                    continue
                index += 1
                yield frame

        self.frame_count = index
        if clock.shifts:
            self.warnings.append(f"The recorder's clock jumped {clock.describe()} (daylight saving time); the match time is corrected")
        if last_line_bad:
            self.warnings.append("Last line is truncated (recording was cut off); ignored")
        if bad_lines:
            self.warnings.append(f"{bad_lines} unreadable line(s) skipped")
        if self.repair:
            how = "Repaired (aggressive)" if self.repair == "aggressive" else "Repaired"
            self.warnings.insert(0, f"{how}: {index:,} readable frames recovered" + "".join(f"; {n}" for n in notes))
        if index < 2:
            raise IncompleteReplay(f"Replay has {index} readable frame(s); at least 2 are needed")


def open_replay(path: Path, max_uncompressed_bytes: int = MAX_UNCOMPRESSED_BYTES, repair: bool | str = False) -> ParsedReplay:
    return ParsedReplay(path, max_uncompressed_bytes, repair)
