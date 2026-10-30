"""Streaming reader for .echoreplay files (zip or plain text, one `<timestamp>\\t<json>` frame per line)."""

import struct
import zipfile
import zlib
from collections.abc import Iterator
from contextlib import contextmanager
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


@contextmanager
def _open_lines(path: Path, max_bytes: int, repair: bool = False, notes: list[str] | None = None,
                chunk_size: int = READ_CHUNK):
    """Yield (container, iterator of raw byte lines)."""
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


class ParsedReplay:
    """Metadata is read on construction; frames() streams the file again from the start."""

    def __init__(self, path: Path, max_uncompressed_bytes: int = MAX_UNCOMPRESSED_BYTES, repair: bool = False):
        """repair=True (D36): salvage mode for damaged files — damaged zips are read up to the damage,
        unreadable lines (including the first) are skipped without limit."""
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
                    frame = build_frame(index, timestamp, data)
                except BAD_LINE_ERRORS:
                    last_line_bad = True
                    continue
                index += 1
                yield frame

        self.frame_count = index
        if last_line_bad:
            self.warnings.append("Last line is truncated (recording was cut off); ignored")
        if bad_lines:
            self.warnings.append(f"{bad_lines} unreadable line(s) skipped")
        if self.repair:
            self.warnings.insert(0, f"Repaired: {index:,} readable frames recovered" + "".join(f"; {n}" for n in notes))
        if index < 2:
            raise IncompleteReplay(f"Replay has {index} readable frame(s); at least 2 are needed")


def open_replay(path: Path, max_uncompressed_bytes: int = MAX_UNCOMPRESSED_BYTES, repair: bool = False) -> ParsedReplay:
    return ParsedReplay(path, max_uncompressed_bytes, repair)
