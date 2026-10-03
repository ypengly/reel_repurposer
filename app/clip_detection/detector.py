"""Transparent, heuristic clip detection. Scores are a 'Content Strength Score', not a virality prediction."""
from __future__ import annotations
import re
from dataclasses import dataclass, field
from app.transcription.models import Segment

PRESETS = {"Quick": (15, 30), "Standard": (30, 60), "Extended": (60, 90)}
END_PUNCT = (".", "?", "!")
HOOK_PAT = re.compile(r"\b(mistake|secret|nobody|never|biggest|truth|stop|why|how to|learned|wish|problem|realized)\b", re.I)
STORY_PAT = re.compile(r"\b(i was|when i|years ago|one day|i remember|i thought|i started|then i)\b", re.I)
EDU_PAT = re.compile(r"\b(you can|you should|you need|the key|step|tip|because|for example|here's how|works)\b", re.I)
EMO_PAT = re.compile(r"\b(love|hate|afraid|scared|proud|hurt|amazing|terrible|cried|struggle|fear|happy)\b", re.I)
BIZ_PAT = re.compile(r"\b(business|revenue|customers?|sales|startup|money|clients?|profit|market)\b", re.I)
FUNNY_PAT = re.compile(r"\b(funny|joke|lol|hilarious|laughed|haha)\b", re.I)
CONTRO_PAT = re.compile(r"\b(wrong|overrated|myth|disagree|controversial|unpopular)\b", re.I)
TUT_PAT = re.compile(r"\b(first|second|next|then|finally|click|open|select|step \d)\b", re.I)
FILLER = re.compile(r"^(and|but|so|because|which|also|then)\b", re.I)


@dataclass
class Clip:
    start: float
    end: float
    text: str
    score: int = 0
    criteria: dict[str, int] = field(default_factory=dict)
    categories: list[str] = field(default_factory=list)
    reasons: list[str] = field(default_factory=list)
    title: str = ""
    hook: str = ""
    favorite: bool = False
    exported: bool = False

    @property
    def duration(self) -> float:
        return self.end - self.start


def split_sentences(segs: list[Segment]) -> list[Segment]:
    """Merge whisper segments into sentence-ish units using end punctuation."""
    out, cur = [], None
    for s in segs:
        cur = Segment(cur.start, s.end, cur.text + " " + s.text.strip(), cur.words + s.words) if cur else \
            Segment(s.start, s.end, s.text.strip(), list(s.words))
        if cur.text.rstrip().endswith(END_PUNCT):
            out.append(cur); cur = None
    if cur:
        out.append(cur)
    return out


def categorize(text: str) -> list[str]:
    cats = []
    if HOOK_PAT.search(text[:120]): cats.append("Strong Hook")
    if EDU_PAT.search(text): cats.append("Educational")
    if STORY_PAT.search(text): cats.append("Story")
    if EMO_PAT.search(text): cats.append("Emotional")
    if BIZ_PAT.search(text): cats.append("Business")
    if FUNNY_PAT.search(text): cats.append("Funny")
    if CONTRO_PAT.search(text): cats.append("Controversial")
    if TUT_PAT.search(text) and len(TUT_PAT.findall(text)) >= 3: cats.append("Tutorial")
    if "?" in text and text.count("?") >= 1 and len(text) < 600: cats.append("Q&A")
    return cats or ["Insight"]


def score_clip(text: str, dur: float, lo: float, hi: float, first: Segment, last: Segment) -> tuple[int, dict, list]:
    c: dict[str, int] = {}
    reasons: list[str] = []
    c["hook"] = 20 if HOOK_PAT.search(first.text) else (12 if "?" in first.text else 6)
    if c["hook"] >= 12: reasons.append("Strong opening statement")
    c["clarity"] = 15 if not FILLER.match(first.text) and first.text[:1].isupper() else 6
    if c["clarity"] == 15: reasons.append("Clear context (starts a fresh thought)")
    c["completeness"] = 15 if last.text.rstrip().endswith(END_PUNCT) else 5
    if c["completeness"] == 15: reasons.append("Complete idea (ends on a full sentence)")
    words = max(1, len(text.split()))
    c["usefulness"] = min(15, 5 + 3 * len(EDU_PAT.findall(text)))
    if c["usefulness"] >= 11: reasons.append("Useful takeaway")
    c["emotion"] = min(10, 2 + 4 * len(EMO_PAT.findall(text)) + 3 * len(STORY_PAT.findall(text)))
    if c["emotion"] >= 6: reasons.append("Personal / emotional relevance")
    wps = words / max(dur, 1)
    c["pacing"] = 10 if 1.8 <= wps <= 3.6 else 5
    if c["pacing"] == 10: reasons.append("Good speaking pace")
    mid = (lo + hi) / 2
    c["duration"] = round(15 * max(0.0, 1 - abs(dur - mid) / max(mid, 1)))
    reasons.append(f"{dur:.0f} seconds")
    return min(100, sum(c.values())), c, reasons


def detect_clips(segs: list[Segment], min_s: float = 30, max_s: float = 60, max_clips: int = 40,
                 min_score: int = 40) -> list[Clip]:
    sents = split_sentences(segs)
    cands: list[Clip] = []
    for i in range(len(sents)):
        for j in range(i, len(sents)):
            dur = sents[j].end - sents[i].start
            if dur > max_s: break
            if dur < min_s: continue
            text = " ".join(s.text for s in sents[i:j + 1])
            sc, crit, why = score_clip(text, dur, min_s, max_s, sents[i], sents[j])
            cl = Clip(sents[i].start, sents[j].end, text, sc, crit, categorize(text), why)
            cl.hook = sents[i].text[:100]
            cl.title = make_titles(cl)[0]
            cands.append(cl)
    cands.sort(key=lambda c: c.score, reverse=True)
    chosen: list[Clip] = []
    for c in cands:  # greedy non-overlapping selection
        if c.score >= min_score and all(c.end <= k.start or c.start >= k.end for k in chosen):
            chosen.append(c)
        if len(chosen) >= max_clips: break
    return sorted(chosen, key=lambda c: c.start)


def make_titles(clip: Clip) -> list[str]:
    first = re.sub(r"[^\w\s']", "", clip.hook or clip.text.split(".")[0]).strip()
    short = " ".join(first.split()[:6]).title()
    base = [short]
    if "Business" in clip.categories: base.append("A Business Lesson Worth Hearing")
    if "Story" in clip.categories: base.append("What I Learned The Hard Way")
    if "Educational" in clip.categories: base.append("A Practical Tip You Can Use")
    base.append("One Idea Worth Remembering")
    return base[:4]


def make_hooks(clip: Clip, n: int = 5) -> list[str]:
    opener = clip.text.split(".")[0].strip()
    pool = ["I wish someone told me this earlier.", "I learned this the hard way.",
            "Nobody warned me about this.", "If this sounds familiar, listen closely.",
            "This changed how I think about it.", f"\"{opener[:80]}\""]
    if "Business" in clip.categories:
        pool.insert(0, "If you're building a business, don't make this mistake.")
    return pool[:n]


CTAS = {"Engagement": "What do you think?", "Follow": "Follow for more practical lessons.",
        "Comment": "Have you experienced this?", "Save": "Save this for later.", "None": ""}


def make_description(clip: Clip, cta: str = "Engagement") -> str:
    tags = " ".join("#" + re.sub(r"\W", "", c.lower()) for c in clip.categories[:3])
    parts = [clip.hook.rstrip(".") + "...", CTAS.get(cta, ""), tags]
    return "\n\n".join(p for p in parts if p)
