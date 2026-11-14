"""Sealed regional content snapshots and explicit, dependency-checked previews.

Hashes provide reproducibility/integrity, not publisher authentication. Real-game
release metadata is supported as data, never as an executable hero implementation.
"""
import copy
from datetime import date
from functools import wraps
import json
import re
from urllib.parse import urlsplit

from .errors import EngineError
from .schema import canonical, digest, integer, keys, validate_fixture_hero

ENTRY_FIELDS = ["id", "revision", "kind", "fidelity", "mechanics", "dependencies",
                "releases", "payload"]
SNAPSHOT_FIELDS = ["schema_version", "snapshot_id", "mode", "region", "patch", "as_of",
                   "ruleset", "fidelity", "entries", "lineage", "content_digest"]
KINDS = {"hero", "soldier", "equipment", "skill", "map", "mechanic", "upgrade", "draft"}
FIDELITIES = {"synthetic_fixture", "release_metadata"}


def checked(function):
    @wraps(function)
    def call(*args, **kwargs):
        try:
            return function(*args, **kwargs)
        except EngineError:
            raise
        except (KeyError, TypeError, ValueError, RecursionError) as error:
            raise EngineError(f"malformed content input for {function.__name__}") from error
    return call


def token(value, name):
    if not isinstance(value, str) or not re.fullmatch(r"[a-z0-9][a-z0-9_.-]{0,95}", value):
        raise EngineError(f"{name} must be a lowercase identifier (at most 96 characters)")
    return value


def iso_date(value, name):
    if not isinstance(value, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
        raise EngineError(f"{name} must be an ISO calendar date")
    try:
        return date.fromisoformat(value)
    except ValueError as error:
        raise EngineError(f"invalid {name}") from error


def bounded_list(value, name, maximum=1000, nonempty=False):
    if not isinstance(value, list) or len(value) > maximum or (nonempty and not value):
        raise EngineError(f"{name} must be a {'nonempty ' if nonempty else ''}list, max {maximum}")
    return value


def reference(value):
    keys(value, ["id", "revision"], "content reference")
    return token(value["id"], "content id"), token(value["revision"], "content revision")


def ref_for(entry):
    return {"id": entry["id"], "revision": entry["revision"]}


def check_entry(entry):
    keys(entry, ENTRY_FIELDS, "content entry")
    identity = reference(ref_for(entry))
    if entry["kind"] not in KINDS or entry["fidelity"] not in FIDELITIES:
        raise EngineError("unknown content kind or fidelity")
    if entry["fidelity"] == "synthetic_fixture":
        if not entry["id"].startswith("fixture_") or not isinstance(entry["payload"], dict):
            raise EngineError("synthetic content needs fixture_ id and explicit payload")
    elif entry["id"].startswith("fixture_") or entry["payload"] is not None:
        raise EngineError("real release metadata must have no executable payload")
    mechanics = bounded_list(entry["mechanics"], "mechanics", 100, nonempty=True)
    for mechanic in mechanics:
        token(mechanic, "mechanic id")
    if len(set(mechanics)) != len(mechanics):
        raise EngineError("duplicate mechanic")
    dependencies = [reference(d) for d in bounded_list(entry["dependencies"], "dependencies", 100)]
    if len(dependencies) != len(set(dependencies)):
        raise EngineError("duplicate dependency")
    keys(entry["releases"], ["global", "cn"], "regional releases")
    for region, release in entry["releases"].items():
        if release is None:  # Unknown or unannounced. Never infer a date.
            continue
        keys(release, ["since", "until", "published_on", "source"], f"{region} release")
        since = iso_date(release["since"], "effective release date")
        if release["until"] is not None and iso_date(release["until"], "availability end") <= since:
            raise EngineError("availability end must be after release date")
        iso_date(release["published_on"], "publication date")
        source = release["source"]
        if not isinstance(source, str) or len(source) > 2048:
            raise EngineError("invalid release source")
        if entry["fidelity"] == "synthetic_fixture":
            if not source.startswith("fixture:"):
                raise EngineError("synthetic release sources must be labelled fixture:")
        else:
            url = urlsplit(source)
            if url.scheme != "https" or not url.hostname or url.username or url.password:
                raise EngineError("real release metadata needs a public HTTPS evidence URL")
    return identity


def catalog_index(catalog):
    keys(catalog, ["schema_version", "catalog_id", "entries"], "catalog")
    integer(catalog["schema_version"], "catalog schema_version", 1, 1)
    token(catalog["catalog_id"], "catalog_id")
    index = {}
    for entry in bounded_list(catalog["entries"], "catalog entries", nonempty=True):
        identity = check_entry(entry)
        if identity in index:
            raise EngineError(f"duplicate catalog revision: {identity}")
        index[identity] = entry
    return index


def selected_index(entries):
    result = {}
    for entry in bounded_list(entries, "snapshot entries", nonempty=True):
        check_entry(entry)
        if entry["id"] in result:
            raise EngineError(f"multiple active revisions of {entry['id']}")
        result[entry["id"]] = entry
    return result


def check_dependencies(entries):
    index = selected_index(entries)
    visited, visiting = set(), set()

    def visit(content_id):
        if len(visiting) >= 64:
            raise EngineError("content dependency depth exceeds 64")
        if content_id in visiting:
            raise EngineError(f"cyclic content dependency at {content_id}")
        if content_id in visited:
            return
        visiting.add(content_id)
        for ref in index[content_id]["dependencies"]:
            key, revision = reference(ref)
            if key not in index or index[key]["revision"] != revision:
                raise EngineError(f"missing exact dependency: {key}@{revision}")
            visit(key)
        visiting.remove(content_id)
        visited.add(content_id)

    for key in index:
        visit(key)


def check_available(entry, region, as_of):
    release = entry["releases"][region]
    if (release is None or as_of < iso_date(release["since"], "release date")
            or (release["until"] is not None and as_of >= iso_date(release["until"], "availability end"))):
        raise EngineError(f"unavailable content: {entry['id']}@{entry['revision']} in {region} on {as_of}")


def seal(body):
    # JSON round-trip also breaks shared references between preview entries and
    # embedded lineage; deepcopy would preserve aliases across those branches.
    return json.loads(canonical({**body, "content_digest": digest(body)}))


@checked
def build_snapshot(catalog, manifest):
    keys(manifest, ["schema_version", "snapshot_id", "mode", "patch", "as_of", "ruleset", "entries"],
         "snapshot manifest")
    integer(manifest["schema_version"], "manifest schema_version", 1, 1)
    if manifest["mode"] not in ("global_live", "cn_live"):
        raise EngineError("build only accepts live modes; use explicit preview composition")
    index = catalog_index(catalog)
    entries = []
    for ref in bounded_list(manifest["entries"], "manifest entries", nonempty=True):
        identity = reference(ref)
        if identity not in index:
            raise EngineError(f"unknown exact content revision: {identity}")
        entries.append(index[identity])
    fidelities = {entry["fidelity"] for entry in entries}
    if len(fidelities) != 1:
        raise EngineError("cannot mix release metadata and synthetic executable content")
    body = {key: manifest[key] for key in
            ("schema_version", "snapshot_id", "mode", "patch", "as_of", "ruleset")}
    body.update(region="global" if body["mode"] == "global_live" else "cn",
                fidelity=next(iter(fidelities)), entries=sorted(entries, key=lambda e: e["id"]),
                lineage=None)
    snapshot = seal(body)
    verify_snapshot(snapshot)
    return snapshot


def overlay_entries(baseline, source, changes):
    result = selected_index(baseline["entries"])
    available = {(e["id"], e["revision"]): e for e in source["entries"]}
    seen = set()
    for ref in bounded_list(changes, "preview changes", 100, nonempty=True):
        content_id, revision = reference(ref)
        if content_id in seen:
            raise EngineError("a preview can replace a content id only once")
        seen.add(content_id)
        if (content_id, revision) not in available:
            raise EngineError(f"preview revision missing from China source: {content_id}@{revision}")
        candidate = available[(content_id, revision)]
        old = result.get(content_id)
        if old is not None and old["revision"] == revision:
            if canonical(old) != canonical(candidate):
                raise EngineError("same id/revision has conflicting content; bump the revision")
            raise EngineError(f"preview change is already in baseline: {content_id}@{revision}")
        result[content_id] = candidate
    return sorted(result.values(), key=lambda e: e["id"])


@checked
def build_preview(baseline, source, changes, snapshot_id):
    verify_snapshot(baseline, allow_preview=False)
    verify_snapshot(source, allow_preview=False)
    body = {key: baseline[key] for key in
            ("schema_version", "region", "patch", "as_of", "ruleset", "fidelity")}
    body.update(snapshot_id=snapshot_id, mode="global_preview",
                entries=overlay_entries(baseline, source, changes),
                lineage={"baseline": baseline, "source": source,
                         "changes": sorted(changes, key=lambda ref: ref["id"])})
    snapshot = seal(body)
    verify_snapshot(snapshot)
    return snapshot


@checked
def verify_snapshot(snapshot, allow_preview=True):
    keys(snapshot, SNAPSHOT_FIELDS, "content snapshot")
    integer(snapshot["schema_version"], "snapshot schema_version", 1, 1)
    for field in ("snapshot_id", "patch", "ruleset"):
        token(snapshot[field], field)
    as_of = iso_date(snapshot["as_of"], "snapshot as_of")
    if snapshot["mode"] not in ("global_live", "cn_live", "global_preview"):
        raise EngineError("unknown experiment mode")
    region = "cn" if snapshot["mode"] == "cn_live" else "global"
    if snapshot["region"] != region or snapshot["fidelity"] not in FIDELITIES:
        raise EngineError("snapshot region/mode or fidelity mismatch")
    body = {key: value for key, value in snapshot.items() if key != "content_digest"}
    if snapshot["content_digest"] != digest(body):
        raise EngineError("content snapshot digest mismatch")
    index = selected_index(snapshot["entries"])
    if canonical(snapshot["entries"]) != canonical(sorted(index.values(), key=lambda e: e["id"])):
        raise EngineError("snapshot entries must be sorted by stable content id")
    if any(entry["fidelity"] != snapshot["fidelity"] for entry in index.values()):
        raise EngineError("snapshot mixes incompatible fidelity levels")
    check_dependencies(snapshot["entries"])
    if snapshot["mode"] == "global_preview":
        if not allow_preview:
            raise EngineError("nested previews are not supported")
        lineage = snapshot["lineage"]
        keys(lineage, ["baseline", "source", "changes"], "preview lineage")
        base, source = lineage["baseline"], lineage["source"]
        verify_snapshot(base, allow_preview=False)
        verify_snapshot(source, allow_preview=False)
        if base["mode"] != "global_live" or source["mode"] != "cn_live":
            raise EngineError("preview requires a Global baseline and China source")
        if any(snapshot[k] != base[k] for k in ("region", "patch", "as_of", "ruleset", "fidelity")):
            raise EngineError("preview changed its Global baseline metadata")
        if any(source[k] != base[k] for k in ("ruleset", "fidelity")):
            raise EngineError("preview source uses an incompatible ruleset/fidelity")
        source_revisions = {(e["id"], e["revision"]): e for e in source["entries"]}
        for entry in base["entries"]:
            other = source_revisions.get((entry["id"], entry["revision"]))
            if other is not None and canonical(entry) != canonical(other):
                raise EngineError("same id/revision differs across regional snapshots")
        expected = overlay_entries(base, source, lineage["changes"])
        if canonical(expected) != canonical(snapshot["entries"]):
            raise EngineError("preview contains undeclared changes")
    else:
        if snapshot["lineage"] is not None:
            raise EngineError("live snapshots cannot have preview lineage")
        for entry in index.values():
            check_available(entry, region, as_of)
    return experiment_metadata(snapshot)


def experiment_metadata(snapshot):
    result = {key: snapshot[key] for key in
              ("snapshot_id", "content_digest", "mode", "region", "patch", "as_of", "fidelity")}
    if snapshot["mode"] == "global_preview":
        result.update(baseline_digest=snapshot["lineage"]["baseline"]["content_digest"],
                      source_digest=snapshot["lineage"]["source"]["content_digest"],
                      changes=copy.deepcopy(snapshot["lineage"]["changes"]))
    return result


def validate_runtime_binding(snapshot, config):
    verify_snapshot(snapshot)
    if snapshot["ruleset"] != config["ruleset"] or snapshot["fidelity"] != "synthetic_fixture":
        raise EngineError("real regional combat is not implemented; release metadata cannot run as fixture")
    expected = {"hero": "fixture.unit.v0", "map": "fixture.map.v0", "draft": "fixture.draft.v0"}
    entries = selected_index(snapshot["entries"])
    for entry in entries.values():
        if entry["kind"] not in expected or entry["mechanics"] != [expected[entry["kind"]]]:
            raise EngineError(f"unsupported executable mechanics: {entry['id']}@{entry['revision']}")
        if entry["kind"] == "hero" and validate_fixture_hero(entry["payload"]) != entry["id"]:
            raise EngineError("fixture hero payload id differs from catalog id")
    for kind, field in (("map", "map"), ("draft", "draft")):
        records = [e for e in entries.values() if e["kind"] == kind]
        if len(records) != 1 or canonical(records[0]["payload"]) != canonical(config[field]):
            raise EngineError(f"scenario {field} does not match its frozen snapshot")
    for box in config["boxes"]:
        for hero in box:
            record = entries.get(hero["id"])
            if (record is None or record["kind"] != "hero"
                    or canonical(record["payload"]) != canonical(hero)):
                raise EngineError(f"hero loadout is not in the frozen snapshot: {hero['id']}")


def bind_snapshot(config, snapshot):
    from .game import validate_config
    if not isinstance(config, dict):
        raise EngineError("scenario must be an object")
    return validate_config({**config, "content_snapshot": copy.deepcopy(snapshot)})
