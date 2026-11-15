"""Explicit-hit accounting probe; not an executable Langrisser ruleset."""

from .errors import EngineError


def simulate_hits(defender_soldier_hp, defender_hero_hp, hits):
    """Apply already resolved integer hits in caller-supplied order.

    Each hit targets the first living soldier or the hero. Excess damage from
    a hit on a soldier is discarded. This is a research hypothesis, not a
    claim about animation timing, targeting, crits or Global battle rules.
    """
    if (not isinstance(defender_soldier_hp, list)
            or len(defender_soldier_hp) > 12
            or not all(type(hp) is int and hp >= 0 for hp in defender_soldier_hp)
            or type(defender_hero_hp) is not int or defender_hero_hp < 0
            or not isinstance(hits, list) or len(hits) > 80):
        raise EngineError("invalid hit sequence lab state")
    soldiers = defender_soldier_hp.copy()
    hero = defender_hero_hp
    events = []
    for index, hit in enumerate(hits):
        if (not isinstance(hit, dict) or set(hit) != {"source", "to_soldier", "to_hero"}
                or hit["source"] not in ("hero", "soldier")
                or any(type(hit[key]) is not int or hit[key] < 0
                       for key in ("to_soldier", "to_hero"))):
            raise EngineError(f"invalid hit at index {index}")
        living = next((i for i, hp in enumerate(soldiers) if hp > 0), None)
        if hero == 0:
            target, damage, applied = "none", 0, 0
        elif living is not None:
            target = f"soldier:{living}"
            damage = hit["to_soldier"]
            applied = min(damage, soldiers[living])
            soldiers[living] -= applied
        else:
            target = "hero"
            damage = hit["to_hero"]
            applied = min(damage, hero)
            hero -= applied
        events.append({"index": index, "source": hit["source"], "target": target,
                       "attempted": damage, "applied": applied,
                       "excess": damage - applied})
    return {"soldier_hp": soldiers, "hero_hp": hero, "events": events}
