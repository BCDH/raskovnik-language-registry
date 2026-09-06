"""Native structural checks for the editable TEI registry."""
from xml.etree import ElementTree as ET
from registry_standards import canonical_language_tag, normalized, technical_id
TEI_NS = "http://www.tei-c.org/ns/1.0"
XML_NS = "http://www.w3.org/XML/1998/namespace"
LANGUAGES = ("sr", "en", "de")
CLASSIFICATION_STATUSES = {"reviewed", "tentative", "disputed"}
class RegistryIntegrityError(ValueError):
    pass

def qname(namespace: str, local_name: str) -> str:
    return f"{{{namespace}}}{local_name}"

def validate_registry(registry_bytes: bytes) -> None:
    try:
        root = ET.fromstring(registry_bytes)
    except ET.ParseError as exc:
        raise RegistryIntegrityError(f"generated registry is not well-formed: {exc}") from exc
    if root.tag != qname(TEI_NS, "TEI") or root.get("type") != "lex-0":
        raise RegistryIntegrityError("registry root must be TEI type=lex-0")
    if root.find(f"./{qname(TEI_NS, 'teiHeader')}/{qname(TEI_NS, 'profileDesc')}/{qname(TEI_NS, 'langUsage')}") is None:
        raise RegistryIntegrityError("registry display tree is not under profileDesc/langUsage")
    if root.find(f"./{qname(TEI_NS, 'text')}/{qname(TEI_NS, 'body')}/{qname(TEI_NS, 'p')}") is None:
        raise RegistryIntegrityError("registry requires explanatory text/body content")
    version_changes = root.findall(
        f"./{qname(TEI_NS, 'teiHeader')}/{qname(TEI_NS, 'revisionDesc')}/{qname(TEI_NS, 'change')}[@type='registryVersion']"
    )
    if (
        len(version_changes) != 1
        or not version_changes[0].get("n")
        or not version_changes[0].get("when")
    ):
        raise RegistryIntegrityError("registry must embed exactly one matching registry version change")
    for forbidden in ("taxonomy", "category", "xenoData"):
        if root.find(f".//{qname(TEI_NS, forbidden)}") is not None:
            raise RegistryIntegrityError(f"forbidden TEI element in registry: {forbidden}")
    nodes = root.findall(f".//{qname(TEI_NS, 'languageGrp')}") + root.findall(
        f".//{qname(TEI_NS, 'language')}"
    )
    canonical_codes: set[str] = set()
    xml_ids: set[str] = set()
    for element in root.iter():
        identifier = element.get(qname(XML_NS, "id"))
        if identifier:
            if identifier in xml_ids:
                raise RegistryIntegrityError(f"duplicate xml:id {identifier!r}")
            xml_ids.add(identifier)
    for node in nodes:
        identifier = canonical_language_tag(node.get("ident", ""))
        if identifier in canonical_codes:
            raise RegistryIntegrityError(f"duplicate canonical node {identifier!r}")
        canonical_codes.add(identifier)
        bcp47 = [child for child in node.findall(qname(TEI_NS, "ident")) if child.get("type") == "BCP47"]
        if len(bcp47) != 1 or normalized(bcp47[0].text or "") != identifier:
            raise RegistryIntegrityError(f"node {identifier!r} must contain one matching BCP47 identifier")
        if bcp47[0].get(qname(XML_NS, "id")) != technical_id(identifier):
            raise RegistryIntegrityError(f"node {identifier!r} has a nonderived technical xml:id")
        if node.tag == qname(TEI_NS, "language") and node.get("role") != "objectLanguage":
            raise RegistryIntegrityError(f"leaf language {identifier!r} must have role=objectLanguage")
        if node.tag == qname(TEI_NS, "languageGrp") and node.get("role") is not None:
            raise RegistryIntegrityError(f"language group {identifier!r} cannot carry role")
        direct_child_nodes = [
            child
            for child in list(node)
            if child.tag in {qname(TEI_NS, "language"), qname(TEI_NS, "languageGrp")}
        ]
        if bool(direct_child_nodes) != (node.tag == qname(TEI_NS, "languageGrp")):
            raise RegistryIntegrityError(f"node {identifier!r} physical element does not match child presence")
        preferred = [
            child
            for child in node.findall(qname(TEI_NS, "name"))
            if child.get("type") == "languageName" and child.get("role") == "languageReferenceName"
        ]
        preferred_languages = [child.get(qname(XML_NS, "lang")) for child in preferred]
        selectable = node.find(qname(TEI_NS, "note") + "[@type='selectionStatus']").get("subtype") == "selectable"
        required_languages = set(LANGUAGES) if selectable else {"en"}
        if (len(preferred_languages) != len(set(preferred_languages))
                or not required_languages <= set(preferred_languages) <= set(LANGUAGES)
                or any(not normalized(child.text or "") for child in preferred)):
            raise RegistryIntegrityError(f"node {identifier!r} lacks valid preferred labels")
        status_notes = [
            child
            for child in node.findall(qname(TEI_NS, "note"))
            if child.get("type") == "classificationStatus"
        ]
        if len(status_notes) != 1 or status_notes[0].get("subtype") not in CLASSIFICATION_STATUSES:
            raise RegistryIntegrityError(f"node {identifier!r} lacks one controlled classification status")
        if len(node.findall(qname(TEI_NS, "settingDesc"))) > 1:
            raise RegistryIntegrityError(f"node {identifier!r} must consolidate locations in one settingDesc")
        profile_notes = [
            child
            for child in node.findall(qname(TEI_NS, "note"))
            if child.get("type") == "tagProfile" and child.get("subtype") == "direct"
        ]
        for profile in profile_notes:
            profile_code = normalized(profile.text or "")
            if profile_code != identifier or profile.get(qname(XML_NS, "id")) != f"profile-{profile_code}":
                raise RegistryIntegrityError(f"node {identifier!r} has a malformed direct tag-profile marker")
        for source_label in [
            child
            for child in node.findall(qname(TEI_NS, "name"))
            if child.get("type") == "sourceLabel"
        ]:
            if source_label.get("subtype") not in {"abbreviation", "label-only"}:
                raise RegistryIntegrityError(f"node {identifier!r} has an ambiguous source-label abbreviation state")
            ana_tokens = source_label.get("ana", "").split()
            profile_targets = [token for token in ana_tokens if token.startswith("#profile-")]
            catalog_targets = [token for token in ana_tokens if token.startswith("#catalog-")]
            if (
                len(ana_tokens) != 2
                or len(profile_targets) != 1
                or len(catalog_targets) != 1
                or profile_targets[0][1:] not in xml_ids
                or catalog_targets[0][1:] not in xml_ids
            ):
                raise RegistryIntegrityError(f"source record on {identifier!r} must link one profile and one catalog")
            if profile_targets[0] != f"#profile-{identifier}":
                raise RegistryIntegrityError(f"source record on {identifier!r} links the wrong direct profile")
            record_id = source_label.get(qname(XML_NS, "id"), "")
            localized = [
                child
                for child in node.findall(qname(TEI_NS, "name"))
                if child.get("type") == "sourceRecordLabel" and child.get("corresp") == f"#{record_id}"
            ]
            if len(localized) != 3 or {child.get(qname(XML_NS, "lang")) for child in localized} != set(LANGUAGES):
                raise RegistryIntegrityError(f"source record {record_id!r} lacks one trilingual label set")
        for pointer_element in node.findall(".//*[@source]"):
            pointer = pointer_element.get("source", "")
            if not pointer.startswith("#") or pointer[1:] not in xml_ids:
                raise RegistryIntegrityError(f"node {identifier!r} contains unresolved source pointer {pointer!r}")
        for ref in node.findall(f".//{qname(TEI_NS, 'ref')}[@target]"):
            target = ref.get("target", "")
            if target.startswith("#") and target[1:] not in xml_ids:
                raise RegistryIntegrityError(f"node {identifier!r} contains unresolved target {target!r}")
        direct_geo_path = (
            f"./{qname(TEI_NS, 'settingDesc')}/{qname(TEI_NS, 'place')}/"
            f"{qname(TEI_NS, 'location')}/{qname(TEI_NS, 'geo')}"
        )
        if node.get("type") in {"family", "collective"} and node.find(direct_geo_path) is not None:
            raise RegistryIntegrityError(f"semantic {node.get('type')} node {identifier!r} has a point")
        for geo in node.findall(direct_geo_path):
            parts = normalized(geo.text or "").split(" ")
            if len(parts) != 2:
                raise RegistryIntegrityError(f"node {identifier!r} has malformed geo content")
            try:
                latitude, longitude = map(float, parts)
            except ValueError as exc:
                raise RegistryIntegrityError(f"node {identifier!r} has nonnumeric geo content") from exc
            if not -90 <= latitude <= 90 or not -180 <= longitude <= 180:
                raise RegistryIntegrityError(f"node {identifier!r} has out-of-range geo content")
