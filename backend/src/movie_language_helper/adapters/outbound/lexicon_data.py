"""Small curated English lexicon used by the offline analyzer.

Entries cover idioms, phrasal verbs and informal expressions that are common in
film dialogue and tend to block comprehension for intermediate learners. CEFR
levels are rough estimates for ranking, not certified levels.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from movie_language_helper.domain.analysis import CefrLevel, LearningItemType

# Up to two short words may sit between a separable verb and its particle,
# e.g. "figure it out", "pick the kids up".
_GAP = r"(?:\s+[\w']+){0,2}?"


@dataclass(frozen=True, slots=True)
class LexiconEntry:
    """One expression with the regular expressions that recognise it."""

    lemma: str
    type: LearningItemType
    meaning: str
    cefr: CefrLevel
    patterns: tuple[re.Pattern[str], ...]
    usage_note: str | None = None


def _forms(*forms: str) -> str:
    return "(?:" + "|".join(re.escape(form) for form in forms) + ")"


def phrasal(
    lemma: str,
    verb_forms: tuple[str, ...],
    particle: str,
    meaning: str,
    cefr: CefrLevel,
    *,
    separable: bool = False,
    usage_note: str | None = None,
) -> LexiconEntry:
    """Build a phrasal verb entry from its inflected verb forms and particle."""
    gap = _GAP if separable else ""
    pattern = rf"\b{_forms(*verb_forms)}{gap}\s+{re.escape(particle)}\b"
    return LexiconEntry(
        lemma,
        LearningItemType.PHRASAL_VERB,
        meaning,
        cefr,
        (re.compile(pattern, re.IGNORECASE),),
        usage_note,
    )


def fixed(
    lemma: str,
    item_type: LearningItemType,
    meaning: str,
    cefr: CefrLevel,
    *patterns: str,
    usage_note: str | None = None,
) -> LexiconEntry:
    """Build an entry from explicit regular expressions (default: the lemma)."""
    sources = patterns or (rf"\b{re.escape(lemma)}\b",)
    return LexiconEntry(
        lemma,
        item_type,
        meaning,
        cefr,
        tuple(re.compile(source, re.IGNORECASE) for source in sources),
        usage_note,
    )


_I = LearningItemType.IDIOM
_S = LearningItemType.SLANG
_O = LearningItemType.OTHER_EXPRESSION
_POSS = r"(?:my|your|his|her|its|our|their)"
A2, B1, B2, C1 = CefrLevel.A2, CefrLevel.B1, CefrLevel.B2, CefrLevel.C1

GIVE = ("give", "gives", "gave", "given", "giving")
GET = ("get", "gets", "got", "gotten", "getting")
TAKE = ("take", "takes", "took", "taken", "taking")
COME = ("come", "comes", "came", "coming")
GO = ("go", "goes", "went", "gone", "going")
PUT = ("put", "puts", "putting")
MAKE = ("make", "makes", "made", "making")
LOOK = ("look", "looks", "looked", "looking")
TURN = ("turn", "turns", "turned", "turning")
RUN = ("run", "runs", "ran", "running")
BREAK = ("break", "breaks", "broke", "broken", "breaking")
CALL = ("call", "calls", "called", "calling")
FIGURE = ("figure", "figures", "figured", "figuring")
PICK = ("pick", "picks", "picked", "picking")
HANG = ("hang", "hangs", "hung", "hanging")
BRING = ("bring", "brings", "brought", "bringing")
CARRY = ("carry", "carries", "carried", "carrying")
FIND = ("find", "finds", "found", "finding")
SET = ("set", "sets", "setting")
WORK = ("work", "works", "worked", "working")
SHOW = ("show", "shows", "showed", "shown", "showing")
MESS = ("mess", "messes", "messed", "messing")
SCREW = ("screw", "screws", "screwed", "screwing")
CHILL = ("chill", "chills", "chilled", "chilling")
FREAK = ("freak", "freaks", "freaked", "freaking")
BACK = ("back", "backs", "backed", "backing")
CHECK = ("check", "checks", "checked", "checking")
SORT = ("sort", "sorts", "sorted", "sorting")
FALL = ("fall", "falls", "fell", "fallen", "falling")
PASS = ("pass", "passes", "passed", "passing")
BLOW = ("blow", "blows", "blew", "blown", "blowing")
CUT = ("cut", "cuts", "cutting")
KEEP = ("keep", "keeps", "kept", "keeping")
LET = ("let", "lets", "letting")
PULL = ("pull", "pulls", "pulled", "pulling")
SHUT = ("shut", "shuts", "shutting")
SPILL = ("spill", "spills", "spilled", "spilt", "spilling")
BITE = ("bite", "bites", "bit", "bitten", "biting")
HIT = ("hit", "hits", "hitting")
COST = ("cost", "costs", "costing")
BEAT = ("beat", "beats", "beating")
JUMP = ("jump", "jumps", "jumped", "jumping")

ENTRIES: tuple[LexiconEntry, ...] = (
    # Phrasal verbs
    phrasal("give up", GIVE, "up", "stop trying; quit", B1, separable=True),
    phrasal("give in", GIVE, "in", "stop resisting and accept defeat", B2),
    phrasal("get over", GET, "over", "recover from something bad", B2),
    phrasal("get away with", GET, "away with", "avoid punishment for something", B2),
    phrasal("get along", GET, "along", "have a friendly relationship", B1),
    phrasal("get by", GET, "by", "manage to survive with little", B2),
    phrasal(
        "take off", TAKE, "off", "leave suddenly; or remove clothes", B1, separable=True
    ),
    phrasal("take over", TAKE, "over", "take control of something", B2),
    phrasal("come up with", COME, "up with", "think of an idea or plan", B2),
    phrasal("come across", COME, "across", "find by chance; seem", B2),
    phrasal("go through", GO, "through", "experience something difficult", B2),
    phrasal("put up with", PUT, "up with", "tolerate something unpleasant", B2),
    phrasal(
        "make up", MAKE, "up", "invent a story; or end an argument", B2, separable=True
    ),
    phrasal(
        "make out",
        MAKE,
        "out",
        "see or understand with difficulty; or kiss",
        C1,
        separable=True,
    ),
    phrasal("look into", LOOK, "into", "investigate", B2),
    phrasal("turn down", TURN, "down", "refuse an offer", B2, separable=True),
    phrasal("run into", RUN, "into", "meet someone by chance", B2),
    phrasal("run out of", RUN, "out of", "have no more of something", B1),
    phrasal("break up", BREAK, "up", "end a romantic relationship", B1),
    phrasal("call off", CALL, "off", "cancel", B2, separable=True),
    phrasal("figure out", FIGURE, "out", "understand or solve", B1, separable=True),
    phrasal(
        "pick up", PICK, "up", "collect someone; or learn casually", B1, separable=True
    ),
    phrasal("hang out", HANG, "out", "spend time casually", B1),
    phrasal("hang on", HANG, "on", "wait a moment", B1),
    phrasal(
        "bring up", BRING, "up", "mention a topic; or raise a child", B2, separable=True
    ),
    phrasal("carry on", CARRY, "on", "continue", B1),
    phrasal("find out", FIND, "out", "discover information", B1),
    phrasal(
        "set up",
        SET,
        "up",
        "arrange; or trick someone so they look guilty",
        B2,
        separable=True,
    ),
    phrasal(
        "work out",
        WORK,
        "out",
        "find a solution; or end well; or exercise",
        B1,
        separable=True,
    ),
    phrasal("show up", SHOW, "up", "arrive, often late or unexpectedly", B1),
    phrasal(
        "mess up", MESS, "up", "make a mistake; ruin something", B2, separable=True
    ),
    phrasal(
        "screw up", SCREW, "up", "make a bad mistake (informal)", B2, separable=True
    ),
    phrasal("chill out", CHILL, "out", "relax; calm down (informal)", B2),
    phrasal(
        "freak out",
        FREAK,
        "out",
        "become very scared or upset (informal)",
        B2,
        separable=True,
    ),
    phrasal("back off", BACK, "off", "move away; stop pressuring someone", B2),
    phrasal(
        "check out", CHECK, "out", "look at something interesting", B1, separable=True
    ),
    phrasal("sort out", SORT, "out", "fix or organise a problem", B2, separable=True),
    phrasal(
        "fall apart", FALL, "apart", "break into pieces; lose emotional control", B2
    ),
    phrasal("pass out", PASS, "out", "faint; lose consciousness", B2),
    phrasal("blow up", BLOW, "up", "explode; or get very angry", B2, separable=True),
    phrasal("cut it out", CUT, "it out", "stop doing that (annoyed)", B2),
    phrasal(
        "keep up", KEEP, "up", "move at the same speed; continue", B1, separable=True
    ),
    phrasal("let down", LET, "down", "disappoint someone", B2, separable=True),
    phrasal(
        "pull off", PULL, "off", "succeed at something difficult", C1, separable=True
    ),
    phrasal("shut up", SHUT, "up", "stop talking (rude)", B1, separable=True),
    # Idioms
    fixed(
        "break the ice",
        _I,
        "make people feel relaxed at the start",
        B2,
        rf"\b{_forms(*BREAK)}\s+the\s+ice\b",
    ),
    fixed(
        "spill the beans",
        _I,
        "reveal a secret",
        B2,
        rf"\b{_forms(*SPILL)}\s+the\s+beans\b",
    ),
    fixed(
        "bite the bullet",
        _I,
        "do something unpleasant that you have avoided",
        C1,
        rf"\b{_forms(*BITE)}\s+the\s+bullet\b",
    ),
    fixed(
        "hit the road",
        _I,
        "leave; start a journey",
        B2,
        rf"\b{_forms(*HIT)}\s+the\s+road\b",
    ),
    fixed("hit the sack", _I, "go to bed", B2, rf"\b{_forms(*HIT)}\s+the\s+sack\b"),
    fixed(
        "call it a day",
        _I,
        "stop working for now",
        B2,
        rf"\b{_forms(*CALL)}\s+it\s+a\s+day\b",
    ),
    fixed(
        "pull someone's leg",
        _I,
        "joke by telling someone something untrue",
        C1,
        rf"\b{_forms(*PULL)}\s+(?:\w+'s|{_POSS})\s+leg\b",
    ),
    fixed(
        "cost an arm and a leg",
        _I,
        "be very expensive",
        B2,
        rf"\b{_forms(*COST)}\s+(?:(?:me|you|him|her|us|them)\s+)?an\s+arm\s+and\s+a\s+leg\b",
    ),
    fixed(
        "beat around the bush",
        _I,
        "avoid saying something directly",
        C1,
        rf"\b{_forms(*BEAT)}\s+(?:around|about)\s+the\s+bush\b",
    ),
    fixed("jump the gun", _I, "act too early", C1, rf"\b{_forms(*JUMP)}\s+the\s+gun\b"),
    fixed("under the weather", _I, "slightly ill", B2),
    fixed("on the same page", _I, "in agreement; understanding the same thing", B2),
    fixed(
        "the last straw", _I, "the final problem that makes someone lose patience", B2
    ),
    fixed("a piece of cake", _I, "very easy", B1),
    fixed("once in a blue moon", _I, "very rarely", B2),
    fixed("in hot water", _I, "in trouble", C1),
    fixed("out of the blue", _I, "unexpectedly", B2),
    fixed("the elephant in the room", _I, "an obvious problem nobody talks about", C1),
    fixed("off the record", _I, "not to be made public", C1),
    fixed("no strings attached", _I, "without conditions", C1),
    fixed("long story short", _I, "to summarise", B2),
    fixed(
        "lose one's mind",
        _I,
        "become crazy or extremely upset",
        B2,
        rf"\b(?:lose|loses|lost|losing)\s+{_POSS}\s+mind\b",
    ),
    fixed(
        "keep an eye on",
        _I,
        "watch carefully",
        B1,
        rf"\b{_forms(*KEEP)}\s+an\s+eye\s+on\b",
    ),
    fixed(
        "get cold feet",
        _I,
        "become nervous and want to cancel a plan",
        C1,
        rf"\b{_forms(*GET)}\s+cold\s+feet\b",
    ),
    fixed(
        "cut corners",
        _I,
        "do something cheaply or carelessly",
        C1,
        rf"\b{_forms(*CUT)}\s+corners\b",
    ),
    fixed(
        "let the cat out of the bag",
        _I,
        "reveal a secret by accident",
        C1,
        rf"\b{_forms(*LET)}\s+the\s+cat\s+out\s+of\s+the\s+bag\b",
    ),
    fixed("speak of the devil", _I, "said when the person you mention appears", B2),
    fixed("my bad", _S, "my mistake (informal)", B2),
    # Informal expressions and slang
    fixed(
        "gonna",
        _S,
        "going to (informal speech)",
        A2,
        usage_note="Written form of fast speech; avoid in formal writing.",
    ),
    fixed(
        "wanna",
        _S,
        "want to (informal speech)",
        A2,
        usage_note="Written form of fast speech; avoid in formal writing.",
    ),
    fixed(
        "gotta",
        _S,
        "have got to; must (informal speech)",
        A2,
        usage_note="Written form of fast speech; avoid in formal writing.",
    ),
    fixed("y'all", _S, "you, plural (informal, mainly Southern US)", B2),
    fixed("no way", _O, "expresses surprise or a strong refusal", B1),
    fixed("no kidding", _O, "really?; or that is obvious", B2),
    fixed("big deal", _O, "something important; ironic: not important", B2),
    fixed("for real", _S, "really; seriously (informal)", B2),
    fixed(
        "bail on",
        _S,
        "leave or abandon someone or a plan (informal)",
        C1,
        r"\b(?:bail|bails|bailed|bailing)\s+on\b",
    ),
    fixed("busted", _S, "caught doing something wrong (informal)", B2),
    fixed("bummer", _S, "a disappointing situation (informal)", B2),
    fixed(
        "ripped off",
        _S,
        "charged too much; cheated (informal)",
        B2,
        r"\b(?:rip|rips|ripped|ripping)\s+(?:\w+\s+)?off\b",
    ),
    fixed("hang in there", _O, "keep going in a difficult time", B2),
    fixed("you bet", _O, "certainly; you're welcome", B2),
    fixed("suit yourself", _O, "do what you want (I don't care)", C1),
    fixed(
        "get a grip", _O, "control your emotions", B2, rf"\b{_forms(*GET)}\s+a\s+grip\b"
    ),
)
