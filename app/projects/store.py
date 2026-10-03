"""SQLite project persistence."""
from __future__ import annotations
import json, sqlite3
from dataclasses import asdict
from app.clip_detection.detector import Clip
from app.transcription.models import Segment, Word

SCHEMA = """CREATE TABLE IF NOT EXISTS meta(k TEXT PRIMARY KEY, v TEXT);
CREATE TABLE IF NOT EXISTS transcript(i INTEGER PRIMARY KEY, data TEXT);
CREATE TABLE IF NOT EXISTS clips(i INTEGER PRIMARY KEY, data TEXT);"""


def save_project(path: str, video_path: str, segs: list[Segment], clips: list[Clip], settings: dict) -> None:
    with sqlite3.connect(path) as db:
        db.executescript(SCHEMA + "DELETE FROM meta;DELETE FROM transcript;DELETE FROM clips;")
        db.execute("INSERT INTO meta VALUES('video',?)", (video_path,))
        db.execute("INSERT INTO meta VALUES('settings',?)", (json.dumps(settings),))
        db.executemany("INSERT INTO transcript VALUES(?,?)", [(i, json.dumps(asdict(s))) for i, s in enumerate(segs)])
        db.executemany("INSERT INTO clips VALUES(?,?)", [(i, json.dumps(asdict(c))) for i, c in enumerate(clips)])


def load_project(path: str) -> tuple[str, list[Segment], list[Clip], dict]:
    try:
        with sqlite3.connect(path) as db:
            meta = dict(db.execute("SELECT k,v FROM meta").fetchall())
            segs = []
            for (d,) in db.execute("SELECT data FROM transcript ORDER BY i"):
                o = json.loads(d); segs.append(Segment(o["start"], o["end"], o["text"], [Word(**w) for w in o["words"]]))
            clips = [Clip(**json.loads(d)) for (d,) in db.execute("SELECT data FROM clips ORDER BY i")]
        return meta["video"], segs, clips, json.loads(meta["settings"])
    except (sqlite3.Error, KeyError) as e:
        raise ValueError(f"Not a valid Reel Repurposer project: {e}") from e
