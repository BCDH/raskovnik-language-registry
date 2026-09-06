"""Offline validation against pinned IANA and ISO tables."""
import csv, re, unicodedata
from dataclasses import dataclass
from pathlib import Path

class RegistrySourceError(RuntimeError):
    """Raised when a pinned registry input is malformed or inconsistent."""

@dataclass(frozen=True)
class IanaRecord:
    record_type: str
    identifier: str
    fields: dict[str, tuple[str, ...]]

    @property
    def descriptions(self) -> tuple[str, ...]:
        return self.fields.get("Description", ())

    @property
    def deprecated(self) -> bool:
        return "Deprecated" in self.fields

@dataclass(frozen=True)
class Iso6393Record:
    identifier: str
    part2b: str | None
    part2t: str | None
    part1: str | None
    scope: str
    language_type: str
    reference_name: str

def normalized(value: str) -> str:
    """Return an NFC, collapsed-whitespace value."""
    return unicodedata.normalize("NFC", " ".join(value.split()))

def canonical_language_tag(tag: str) -> str:
    """Validate and canonicalize the BCP 47 subset used by Raskovnik."""
    if not tag or not re.fullmatch(r"[A-Za-z0-9]+(?:-[A-Za-z0-9]+)*", tag):
        raise RegistrySourceError(f"malformed BCP 47 tag {tag!r}")
    parts = tag.split("-")
    if parts[0].lower() == "x":
        if len(parts) < 2 or any(not 1 <= len(part) <= 8 for part in parts[1:]):
            raise RegistrySourceError(f"invalid wholly private language tag {tag!r}")
        canonical = "-".join(part.lower() for part in parts)
        if tag != canonical:
            raise RegistrySourceError(
                f"non-canonical language tag {tag!r}; expected {canonical!r}"
            )
        return canonical

    primary = parts[0]
    if not re.fullmatch(r"[A-Za-z]{2,3}", primary):
        raise RegistrySourceError(f"unsupported primary language subtag in {tag!r}")
    canonical_parts = [primary.lower()]
    private = False
    for part in parts[1:]:
        if private:
            if not 1 <= len(part) <= 8:
                raise RegistrySourceError(f"invalid private subtag {part!r} in {tag!r}")
            canonical_parts.append(part.lower())
            continue
        if part.lower() == "x":
            private = True
            canonical_parts.append("x")
        elif re.fullmatch(r"[A-Za-z]{4}", part):
            canonical_parts.append(part.title())
        elif re.fullmatch(r"[A-Za-z]{2}|[0-9]{3}", part):
            canonical_parts.append(part.upper())
        elif re.fullmatch(r"[A-Za-z0-9]{5,8}|[0-9][A-Za-z0-9]{3}", part):
            canonical_parts.append(part.lower())
        else:
            raise RegistrySourceError(f"unsupported BCP 47 subtag {part!r} in {tag!r}")
    if private and canonical_parts[-1] == "x":
        raise RegistrySourceError(f"private-use marker has no value in {tag!r}")
    canonical = "-".join(canonical_parts)
    if tag != canonical:
        raise RegistrySourceError(
            f"non-canonical language tag {tag!r}; expected {canonical!r}"
        )
    return canonical

def technical_id(code: str) -> str:
    """Derive the one technical XML identifier from a canonical code."""
    return "lang-" + canonical_language_tag(code)

def parse_iana_registry(path: Path) -> tuple[str, dict[tuple[str, str], IanaRecord]]:
    data = path.read_text(encoding="utf-8")
    header, *blocks = data.split("%%")
    date_match = re.search(r"^File-Date:\s*(\d{4}-\d{2}-\d{2})\s*$", header, re.MULTILINE)
    if date_match is None:
        raise RegistrySourceError("IANA registry has no File-Date")
    records: dict[tuple[str, str], IanaRecord] = {}
    for block in blocks:
        fields: dict[str, list[str]] = {}
        current: str | None = None
        for line in block.strip().splitlines():
            if line.startswith(" ") and current is not None:
                fields[current][-1] += " " + line.strip()
                continue
            if ":" not in line:
                continue
            name, value = line.split(":", 1)
            current = name
            fields.setdefault(name, []).append(value.strip())
        record_type = fields.get("Type", [""])[0]
        identifier = fields.get("Subtag", fields.get("Tag", [""]))[0]
        if not record_type or not identifier:
            continue
        key = (record_type, identifier.lower())
        if key in records:
            raise RegistrySourceError(f"duplicate IANA record {key!r}")
        records[key] = IanaRecord(
            record_type,
            identifier,
            {name: tuple(values) for name, values in fields.items()},
        )
    return date_match.group(1), records

def validate_registered_tag(
    tag: str, records: dict[tuple[str, str], IanaRecord]
) -> None:
    """Validate all non-private subtags of a canonical tag against IANA."""
    parts = canonical_language_tag(tag).split("-")
    if parts[0] == "x":
        return
    primary = records.get(("language", parts[0].lower()))
    if primary is None or primary.deprecated:
        raise RegistrySourceError(f"tag {tag!r} has an unavailable primary subtag")
    private_index = next(
        (index for index, part in enumerate(parts[1:], 1) if part.lower() == "x"),
        len(parts),
    )
    prefix_parts = [parts[0]]
    for part in parts[1:private_index]:
        if re.fullmatch(r"[A-Z][a-z]{3}", part):
            record_type = "script"
        elif re.fullmatch(r"[A-Z]{2}|[0-9]{3}", part):
            record_type = "region"
        else:
            record_type = "variant"
        record = records.get((record_type, part.lower()))
        if record is None or record.deprecated:
            raise RegistrySourceError(
                f"tag {tag!r} has unavailable {record_type} subtag {part!r}"
            )
        prefixes = {value.lower() for value in record.fields.get("Prefix", ())}
        if prefixes and "-".join(prefix_parts).lower() not in prefixes:
            raise RegistrySourceError(
                f"variant {part!r} is unavailable for prefix {'-'.join(prefix_parts)!r}"
            )
        prefix_parts.append(part)

def parse_iso639_3(path: Path) -> tuple[
    dict[str, Iso6393Record], dict[str, Iso6393Record], dict[str, Iso6393Record]
]:
    by_id: dict[str, Iso6393Record] = {}
    by_part1: dict[str, Iso6393Record] = {}
    by_part2: dict[str, Iso6393Record] = {}
    with path.open(encoding="utf-8", newline="") as source:
        for row in csv.DictReader(source, delimiter="\t"):
            record = Iso6393Record(
                row["Id"],
                row["Part2b"] or None,
                row["Part2t"] or None,
                row["Part1"] or None,
                row["Scope"],
                row["Language_Type"],
                row["Ref_Name"],
            )
            if record.identifier in by_id:
                raise RegistrySourceError(
                    f"duplicate ISO 639-3 identifier {record.identifier!r}"
                )
            by_id[record.identifier] = record
            if record.part1:
                by_part1[record.part1] = record
            for part2 in (record.part2b, record.part2t):
                if part2:
                    by_part2[part2] = record
    return by_id, by_part1, by_part2
