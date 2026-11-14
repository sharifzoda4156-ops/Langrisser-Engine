"""Small shared validation and canonical hashing primitives."""
import hashlib
import json

from .errors import EngineError


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


def digest(value):
    return hashlib.sha256(canonical(value).encode()).hexdigest()


def integer(value, name, low, high):
    if type(value) is not int or not low <= value <= high:
        raise EngineError(f"{name} must be an integer in [{low}, {high}]")
    return value


def keys(value, required, name):
    if not isinstance(value, dict) or set(value) != set(required):
        raise EngineError(f"{name} requires exactly these fields: {', '.join(required)}")


def validate_fixture_hero(hero):
    keys(hero, ["id", "hp", "attack", "defense", "movement", "range"], "fixture hero")
    hero_id = hero["id"]
    if (not isinstance(hero_id, str) or not hero_id.startswith("fixture_")
            or len(hero_id) > 80 or not hero_id.isascii()
            or not all(c.isalnum() or c == "_" for c in hero_id)):
        raise EngineError("synthetic hero ids must use fixture_ and ASCII letters/digits/_")
    for field, low, high in [("hp", 1, 10000), ("attack", 1, 10000),
                             ("defense", 0, 10000), ("movement", 0, 10), ("range", 1, 10)]:
        integer(hero[field], field, low, high)
    return hero_id
