"""Durable local decision stand: atomic submissions and verified event replay."""
from contextlib import contextmanager
import json
from pathlib import Path
import sqlite3
import uuid

from .errors import Conflict, EngineError, NotFound
from . import __version__
from .game import (apply_action, canonical, current_player, digest, initial_state,
                   integer, keys, legal_actions, observation, state_hash, validate_config, fidelity)


class Stand:
    def __init__(self, database):
        self.database = str(database)
        Path(database).parent.mkdir(parents=True, exist_ok=True)
        with self.connection() as db:
            db.execute("PRAGMA journal_mode=WAL")
            db.executescript("""
                CREATE TABLE IF NOT EXISTS matches (
                    id TEXT PRIMARY KEY, config TEXT NOT NULL, state TEXT NOT NULL,
                    version INTEGER NOT NULL
                );
                CREATE TABLE IF NOT EXISTS decisions (
                    match_id TEXT NOT NULL, version INTEGER NOT NULL,
                    request_id TEXT NOT NULL UNIQUE, payload TEXT NOT NULL,
                    record TEXT NOT NULL, PRIMARY KEY(match_id, version)
                );
            """)

    @contextmanager
    def connection(self):
        db = sqlite3.connect(self.database, timeout=10)
        db.row_factory = sqlite3.Row
        try:
            yield db
            db.commit()
        except BaseException:
            db.rollback()
            raise
        finally:
            db.close()

    @staticmethod
    def load(db, match_id):
        row = db.execute("SELECT * FROM matches WHERE id=?", (match_id,)).fetchone()
        if row is None:
            raise NotFound("match not found")
        return json.loads(row["config"]), json.loads(row["state"]), row["version"]

    def create_match(self, config):
        config = validate_config(config)
        state = initial_state(config)
        # Check the binary before persisting a fixed-team match.
        if state["phase"] == "battle":
            legal_actions(config, state)
        match_id = uuid.uuid4().hex
        with self.connection() as db:
            db.execute("INSERT INTO matches VALUES (?, ?, ?, 0)",
                       (match_id, canonical(config), canonical(state)))
        result = {"match_id": match_id, "version": 0, "ruleset": config["ruleset"],
                  "fidelity": fidelity(config)}
        if "content_snapshot" in config:
            from .content import experiment_metadata
            result["experiment"] = experiment_metadata(config["content_snapshot"])
        return result

    @staticmethod
    def request_for(match_id, config, state, version, player):
        integer(player, "player", 0, 1)
        active = current_player(config, state)
        summary = {"match_id": match_id, "version": version, "current_player": active,
                   "finished": active is None}
        if active != player:
            return {**summary, "waiting": active is not None, "request": None}
        hash_value = state_hash(config, state)
        request_id = digest({"match_id": match_id, "version": version,
                             "player": player, "state_hash": hash_value})
        return {**summary, "waiting": False, "request": {
            "protocol_version": 1, "request_id": request_id, "state_hash": hash_value,
            "player": player, "observation": observation(config, state, player),
            "legal_actions": legal_actions(config, state)}}

    def get_decision_request(self, match_id, player):
        with self.connection() as db:
            config, state, version = self.load(db, match_id)
            return self.request_for(match_id, config, state, version, player)

    def submit_action(self, match_id, payload):
        keys(payload, ["request_id", "state_hash", "expected_version", "player", "action_id"],
             "submission")
        integer(payload["expected_version"], "expected_version", 0, 1000000)
        integer(payload["player"], "player", 0, 1)
        for key in ("request_id", "state_hash", "action_id"):
            if (not isinstance(payload[key], str) or len(payload[key]) != 64
                    or any(c not in "0123456789abcdef" for c in payload[key])):
                raise EngineError(f"{key} must be a lowercase SHA-256 identifier")
        with self.connection() as db:
            db.execute("BEGIN IMMEDIATE")
            config, state, version = self.load(db, match_id)
            previous = db.execute("SELECT * FROM decisions WHERE request_id=?",
                                  (payload["request_id"],)).fetchone()
            if previous is not None:
                if previous["match_id"] != match_id or previous["payload"] != canonical(payload):
                    raise Conflict("request_id already used with a different submission")
                return json.loads(previous["record"])
            if version != payload["expected_version"]:
                raise Conflict("stale version; fetch a fresh decision request")
            if current_player(config, state) != payload["player"]:
                raise Conflict("this player has no pending decision")
            request = self.request_for(match_id, config, state, version, payload["player"])["request"]
            if (request["request_id"] != payload["request_id"]
                    or request["state_hash"] != payload["state_hash"]):
                raise Conflict("decision request does not match current state")
            updated, events = apply_action(config, state, payload["action_id"])
            record = {"match_id": match_id, "version": version + 1,
                      "request_id": payload["request_id"], "player": payload["player"],
                      "action_id": payload["action_id"], "before_hash": request["state_hash"],
                      "after_hash": state_hash(config, updated), "events": events,
                      "finished": updated["phase"] == "finished"}
            db.execute("INSERT INTO decisions VALUES (?, ?, ?, ?, ?)",
                       (match_id, version + 1, payload["request_id"], canonical(payload), canonical(record)))
            db.execute("UPDATE matches SET state=?, version=? WHERE id=?",
                       (canonical(updated), version + 1, match_id))
            return record

    def get_replay(self, match_id):
        with self.connection() as db:
            db.execute("BEGIN")  # One consistent snapshot while players may keep moving.
            config, state, version = self.load(db, match_id)
            rows = db.execute("SELECT payload, record FROM decisions WHERE match_id=? ORDER BY version",
                              (match_id,)).fetchall()
        return {"protocol_version": 1, "engine_version": __version__,
                "fidelity": fidelity(config), "match_id": match_id,
                "config": config, "version": version, "final_state": state,
                "final_hash": state_hash(config, state),
                "decisions": [{"submission": json.loads(row["payload"]),
                               "receipt": json.loads(row["record"])} for row in rows]}


def verify_replay(replay):
    try:
        return _verify_replay(replay)
    except (KeyError, TypeError, IndexError) as error:
        raise EngineError("malformed replay") from error


def _verify_replay(replay):
    keys(replay, ["protocol_version", "engine_version", "fidelity", "match_id", "config",
                  "version", "final_state", "final_hash", "decisions"], "replay")
    if (type(replay["protocol_version"]) is not int or replay["protocol_version"] != 1
            or replay["engine_version"] != __version__):
        raise EngineError("unsupported replay format")
    integer(replay["version"], "replay version", 0, 1000000)
    if not isinstance(replay["decisions"], list):
        raise EngineError("replay decisions must be a list")
    config = validate_config(replay["config"])
    if replay["fidelity"] != fidelity(config):
        raise EngineError("replay fidelity does not match its ruleset")
    state = initial_state(config)
    for version, decision in enumerate(replay["decisions"]):
        player = current_player(config, state)
        if player is None:
            raise EngineError("replay contains actions after match completion")
        request = Stand.request_for(replay["match_id"], config, state, version, player)["request"]
        payload = decision["submission"]
        expected = {"request_id": request["request_id"], "state_hash": request["state_hash"],
                    "expected_version": version, "player": player,
                    "action_id": payload["action_id"]}
        if canonical(payload) != canonical(expected):
            raise EngineError("replay submission mismatch")
        updated, events = apply_action(config, state, payload["action_id"])
        receipt = {"match_id": replay["match_id"], "version": version + 1,
                   "request_id": request["request_id"], "player": player,
                   "action_id": payload["action_id"], "before_hash": request["state_hash"],
                   "after_hash": state_hash(config, updated), "events": events,
                   "finished": updated["phase"] == "finished"}
        if canonical(decision["receipt"]) != canonical(receipt):
            raise EngineError("replay receipt or events mismatch")
        state = updated
    if (replay["version"] != len(replay["decisions"])
            or canonical(replay["final_state"]) != canonical(state)
            or replay["final_hash"] != state_hash(config, state)):
        raise EngineError("replay final state mismatch")
    return {"verified": True, "decisions": len(replay["decisions"]),
            "finished": state["phase"] == "finished", "final_hash": state_hash(config, state)}
