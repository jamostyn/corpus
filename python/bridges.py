"""Citation bridges — indirect connections between corpus papers.

Paper A and paper B may both be in the corpus with no direct citation
between them, yet be linked through a paper that is NOT in the corpus:
A cites M, M cites B. That middle paper is a bridge, and it is often
the thing that explains why two lines of work belong together.

WHY MEET-IN-THE-MIDDLE, NOT A SEARCH
------------------------------------
The obvious approach is to walk outward from A: take its references,
then their references, and so on until B turns up. Measured on the real
corpus (2026-09-17), that costs 64 requests and 18.4s for ONE pair and
usually finds nothing; hop 1 expands to ~58 papers and hop 2 to ~3054.
A third hop would be ~2000 requests per pair.

Meeting in the middle costs ~3000x less and answers every pair at once:

    forward(A)  = the works A references          (local; free)
    backward(B) = the works that cite B           (one request each)
    bridges     = forward(A) & backward(B)

The asymmetry is what makes it cheap. Median references per paper is
58; median CITERS is 24. The backward direction is both smaller and
bounded, and fetching it for the whole corpus is ~70 requests.

WHY A YEAR FILTER IS NOT NEEDED HERE
------------------------------------
The pruning rule — a paper older than the target can never cite it,
because citations point backwards in time — is correct, and it is what
makes an outward SEARCH terminate. At depth 2 it is redundant: every
member of `backward(B)` cites B by construction, so it is already
newer. It would apply to any future depth-3 search, where it does
real work.

Nothing here touches the network or Flask. `collect_*` takes an
already-fetched mapping; the fetching lives in `bridges_api`.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field

logger = logging.getLogger("corpus.bridges")

# Format version for the cached payload. Bump when the on-disk shape
# changes so a stale cache is discarded rather than mis-read.
BRIDGE_CACHE_VERSION = 1

# Bridges reported per ordered pair. A pair sharing 300 middle papers
# is not 300 times more interesting than one sharing 5, and the panel
# has to render it.
MAX_MIDDLES_PER_PAIR = 25


@dataclass
class Bridge:
    """One indirect connection, `src` -> middle work(s) -> `dst`."""
    src: str                       # corpus slug, the newer paper
    dst: str                       # corpus slug, the older paper
    hops: int                      # 2 for src -> M -> dst
    middles: list[str] = field(default_factory=list)   # OpenAlex short ids

    def as_dict(self) -> dict:
        return {"src": self.src, "dst": self.dst, "hops": self.hops,
                "middles": list(self.middles)}


def find_bridges(forward: dict[str, set[str]],
                 backward: dict[str, set[str]],
                 direct: set[tuple[str, str]] | None = None,
                 years: dict[str, int | None] | None = None) -> list[Bridge]:
    """All depth-2 bridges among the corpus papers.

    `forward[slug]`  — OpenAlex ids that slug's paper references.
    `backward[slug]` — OpenAlex ids of works citing slug's paper.
    `direct`         — (src, dst) pairs already linked directly; skipped,
                       because a direct citation is a better answer than
                       a bridge and the connections panel shows it
                       separately.
    `years`          — slug -> publication year. Used ONLY to orient each
                       pair (newer cites older); a pair whose years are
                       unknown is still reported, in both directions,
                       rather than dropped.
    """
    direct = direct or set()
    years = years or {}
    out: list[Bridge] = []
    slugs = sorted(set(forward) | set(backward))

    for a in slugs:
        fa = forward.get(a) or set()
        if not fa:
            continue
        for b in slugs:
            if a == b or (a, b) in direct:
                continue
            ya, yb = years.get(a), years.get(b)
            # Only newer -> older. A paper cannot cite one published
            # after it, so the reverse pair is not a missing result.
            if ya is not None and yb is not None and ya < yb:
                continue
            bb = backward.get(b) or set()
            if not bb:
                continue
            middles = fa & bb
            if middles:
                out.append(Bridge(src=a, dst=b, hops=2,
                                  middles=sorted(middles)[:MAX_MIDDLES_PER_PAIR]))
    # Strongest first: more shared middles is a stronger connection.
    out.sort(key=lambda br: (-len(br.middles), br.src, br.dst))
    logger.info("bridges_computed pairs=%d", len(out))
    return out


def bridges_for(slug: str, bridges: list[dict]) -> list[dict]:
    """Every bridge touching `slug`, from either end, normalised so the
    OTHER paper is always `other`.

    The panel asks "what is this paper connected to", which is
    direction-agnostic; storing one row per ordered pair and flipping
    on read avoids keeping the same fact twice.
    """
    out = []
    for b in bridges:
        if b.get("src") == slug:
            out.append({**b, "other": b.get("dst"), "direction": "cites-via"})
        elif b.get("dst") == slug:
            out.append({**b, "other": b.get("src"), "direction": "cited-via"})
    out.sort(key=lambda b: (-len(b.get("middles") or []), str(b.get("other"))))
    return out
