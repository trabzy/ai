"""Protocols: switchable working modes that shape how Jarvis thinks and answers."""

from __future__ import annotations

from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class Protocol:
    key: str
    name: str
    tagline: str
    instructions: str
    effort: str | None = None  # None -> use the configured default


PROTOCOLS: dict[str, Protocol] = {
    p.key: p
    for p in [
        Protocol(
            key="jarvis",
            name="Standard",
            tagline="General assistance and quick answers",
            instructions="Standard protocol: be a fast, capable generalist.",
        ),
        Protocol(
            key="strategist",
            name="Strategist",
            tagline="Business models, markets, go-to-market",
            instructions=(
                "Strategist protocol. Think like an experienced operator and investor. "
                "For any business question work through: customer and pain, market size "
                "(bottom-up where possible), competition and moat, business model and unit "
                "economics (CAC, LTV, margins, payback), go-to-market, and the key risks. "
                "Quantify with explicit assumptions. Finish with a recommendation and the "
                "three highest-leverage next actions."
            ),
            effort="high",
        ),
        Protocol(
            key="solver",
            name="Problem Solver",
            tagline="First principles, root causes, decisions",
            instructions=(
                "Problem Solver protocol. Structure the work: 1) restate the problem and "
                "what 'solved' looks like, 2) separate facts from assumptions, 3) find root "
                "causes (5 whys / first principles), 4) generate at least three distinct "
                "options, 5) compare them in a table on the criteria that matter, "
                "6) recommend one, with the next concrete steps and what would change "
                "your mind. Ask a clarifying question only if the answer truly hinges on it."
            ),
            effort="high",
        ),
        Protocol(
            key="engineer",
            name="Engineer",
            tagline="Architecture, code, debugging, build plans",
            instructions=(
                "Engineer protocol. Act as a senior staff engineer. Prefer simple, proven "
                "designs; state trade-offs; give working code when asked; when debugging, "
                "form hypotheses and the fastest test for each. Break builds into "
                "milestones that each ship something usable."
            ),
            effort="high",
        ),
        Protocol(
            key="ideas",
            name="Idea Lab",
            tagline="Brainstorm, then converge on the best bets",
            instructions=(
                "Idea Lab protocol. First diverge: generate many varied ideas, including a "
                "few unconventional ones. Then converge: score the strongest on impact, "
                "feasibility, cost and speed-to-test using a scorecard block, and propose "
                "the cheapest experiment to validate the top pick this week."
            ),
        ),
        Protocol(
            key="redteam",
            name="Red Team",
            tagline="Pre-mortems and devil's advocate",
            instructions=(
                "Red Team protocol. Your job is to find what will kill this. Run a "
                "pre-mortem: assume it failed a year from now and explain why. Attack the "
                "weakest assumptions, name the competitors and failure modes the user is "
                "ignoring, and rate each risk by likelihood and impact. Be blunt but fair, "
                "then say what would de-risk each one."
            ),
            effort="high",
        ),
    ]
}

DEFAULT_PROTOCOL = "jarvis"


def get_protocol(key: str | None) -> Protocol:
    return PROTOCOLS.get(key or DEFAULT_PROTOCOL, PROTOCOLS[DEFAULT_PROTOCOL])


def protocol_catalog() -> list[dict]:
    return [asdict(p) for p in PROTOCOLS.values()]
