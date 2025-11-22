from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from services.cj_assessment_service.models_api import EssayForComparison


def _inflate(text: str, repeat: int = 4) -> str:
    """Repeat text to ensure cacheable blocks exceed Anthropic's 1024-token floor."""

    return "\n\n".join(text for _ in range(max(repeat, 1)))


def _build_assessment_context() -> dict[str, str]:
    student_prompt = _inflate(
        (
            "Write a reflective essay that connects a concrete classroom moment to a broader idea "
            "about how people learn. Describe the setting, the specific challenge you faced, and "
            "the actions you took. Explain what changed in your understanding because of that "
            "moment and what you would do differently next time. Keep the tone professional but "
            "personal, and ground your claims in observable details rather than abstractions."
        )
    )

    assessment_instructions = _inflate(
        (
            "Assess clarity, structure, specificity, and evidence of learning. Essays should open "
            "with a concise scene, develop one main insight, and close with a forward-looking "
            "action. High-quality responses cite concrete behaviors, avoid clichés, and show an "
            "ability to translate reflection into an actionable next step. Penalize vague claims, "
            "unsupported generalizations, and repetition."
        )
    )

    judge_rubric = _inflate(
        (
            "Scoring rubric: (1) Scene specificity: names of people, places, or artifacts; "
            "(2) Insight depth: explains why the moment mattered and how it shifted the writer's "
            "approach; (3) Actionability: identifies a clear next step or experiment; "
            "(4) Coherence and concision: logical flow with minimal filler; "
            "(5) Voice and professionalism: respectful tone, student-centered language, and "
            "evidence of ethical reflection. Strong essays balance empathy with precision."
        )
    )

    return {
        "student_prompt_text": student_prompt,
        "assessment_instructions": assessment_instructions,
        "judge_rubric_text": judge_rubric,
    }


_ASSESSMENT_CONTEXT = _build_assessment_context()


def _base_anchors() -> list[EssayForComparison]:
    texts = [
        (
            "During a peer-coaching cycle, I observed a student-led discussion that stalled after "
            "two questions. By pausing and introducing a short wait time protocol, participation "
            "rebounded and quieter students began offering examples. The experience reinforced the "
            "value of silence as an instructional tool and reshaped how I plan group norms."
        ),
        (
            "I redesigned my lab instructions after realizing students copied steps without "
            "understanding the underlying concept. Embedding quick prediction prompts before each "
            "procedure doubled the number of students who could explain the reaction afterwards, "
            "showing me that pacing and pre-commitment matter more than exhaustive detail."
        ),
        (
            "When a debate became unproductive, I switched to a structured 'claim, evidence, "
            "question' round. Students who typically dominate had to slow down, and emergent "
            "questions from quieter peers improved the evidence quality. I learned to treat "
            "discussion formats as interventions, not just containers."
        ),
        (
            "A reading group struggled with metaphor-heavy text until I provided a short visual "
            "analogy. Comprehension checks jumped, but more importantly, students began creating "
            "their own analogies. The shift reminded me that modeling cognitive moves is a "
            "prerequisite for expecting them."
        ),
        (
            "After surveying exit tickets, I noticed many students misapplied a formula on novel "
            "problems. Creating a one-page 'error gallery' that anonymized common mistakes led to "
            "a discussion where students corrected one another. Normalizing error reduced anxiety "
            "and clarified misconceptions faster than my direct explanations."
        ),
        (
            "I piloted a micro-writing routine where students had exactly five minutes to connect "
            "a concept to a personal example. Over two weeks, their responses grew more precise "
            "and self-aware, suggesting that frequency and brevity can build reflective muscle "
            "without overburdening grading."
        ),
        (
            "Introducing a student choice board for project formats increased engagement but also "
            "surfaced inequities in resource access. Creating a shared asset library and pairing "
            "students for feedback balanced creativity with support, reminding me to pair autonomy "
            "with scaffolds."
        ),
        (
            "A newcomer student hesitated to participate until we co-created sentence stems tied "
            "to her interests. Within a week, she initiated questions during labs. The moment "
            "showed me how linguistic access tools can unlock confidence quickly when personalized."
        ),
        (
            "When group roles rotated weekly, accountability wavered. Adding a 'role reflection' "
            "journal helped students articulate what went well and what to change. The quality of "
            "collaboration improved, and students began suggesting new roles on their own."
        ),
        (
            "A trial of spaced retrieval warmups revealed that students retained definitions but "
            "struggled to apply them. Incorporating short application mini-scenarios in the warmup "
            "phase balanced recall with transfer and reduced reteaching later in the unit."
        ),
    ]

    return [
        EssayForComparison(id=f"anchor-{idx + 1}", text_content=text)
        for idx, text in enumerate(texts)
    ]


def _base_essays() -> list[EssayForComparison]:
    texts = [
        (
            "In robotics club, my team kept skipping design sketches, which led to fragile builds. "
            "After a mentor challenged us to prototype on paper first, our robots stopped failing "
            "during stress tests. Planning felt slow at first, but the extra minutes saved hours "
            "of repairs and taught me to test ideas cheaply."
        ),
        (
            "While tutoring a classmate in algebra, I realized I explained steps without checking "
            "for understanding. Switching to having him predict the next move exposed gaps we "
            "fixed together. I learned that asking short diagnostic questions can be more helpful "
            "than giving perfect explanations."
        ),
        (
            "During a group history project, I monopolized research because I feared missing the "
            "deadline. The final presentation felt one-dimensional. Next time I will set explicit "
            "checkpoints and rotate ownership so we capture multiple perspectives and avoid last "
            "minute scrambling."
        ),
        (
            "In debate practice, I got flustered when opponents used unfamiliar evidence. Taking a "
            "breath, restating their claim, and asking for a source bought time and calmed me. I "
            "plan to keep a short checklist for handling surprises instead of reacting defensively."
        ),
        (
            "My science fair project stalled because I tracked results haphazardly. Building a "
            "small spreadsheet with daily prompts uncovered trends I would have missed. The "
            "experience showed me that disciplined data collection is a skill, not busywork."
        ),
        (
            "I led a volunteer workshop on resume writing and realized participants tuned out when "
            "I lectured. Shifting to peer review with sample resumes sparked discussion and "
            "produced better revisions. I learned to design around active practice instead of "
            "extended talk."
        ),
        (
            "While learning guitar, I avoided slow practice and plateaued. Recording myself at "
            "half speed revealed timing issues, and incremental metronome increases finally moved "
            "me forward. Now I embrace deliberate practice even when it feels tedious."
        ),
        (
            "Pairing with a quieter student on a coding assignment taught me to leave longer "
            "pauses after asking questions. Her solutions were strong once she had space to think. "
            "I realized my pace can unintentionally silence collaborators."
        ),
        (
            "I underestimated how much background knowledge younger teammates lacked during a STEM "
            "camp. Building a quick glossary together leveled the field and sped up later tasks. "
            "Next time I'll check shared vocabulary before diving into complex instructions."
        ),
        (
            "During a mock trial, I focused on cross-examination theatrics and neglected case "
            "theory. Our arguments wobbled. Creating a one-page narrative map afterwards helped "
            "me see how each question should support a central claim. I plan to rehearse with that "
            "map before the next round."
        ),
    ]

    return [
        EssayForComparison(id=f"essay-{idx + 1}", text_content=text)
        for idx, text in enumerate(texts)
    ]


_ANCHORS = _base_anchors()
_ESSAYS = _base_essays()


@dataclass(frozen=True)
class BenchmarkFixture:
    """Fixture definition for benchmark workloads."""

    name: str
    assignment_id: str
    assessment_context: dict[str, str]
    anchors: list[EssayForComparison]
    essays: list[EssayForComparison]

    def comparisons(self) -> Iterable[tuple[EssayForComparison, EssayForComparison]]:
        """Yield anchor/student pairs (anchor as Essay A, student as Essay B)."""

        for anchor in self.anchors:
            for essay in self.essays:
                yield anchor, essay


def get_fixture(name: str) -> BenchmarkFixture:
    """Return the requested fixture by name."""

    normalized = name.strip().lower()
    if normalized not in {"smoke", "full"}:
        raise ValueError("Fixture must be 'smoke' or 'full'")

    if normalized == "smoke":
        return BenchmarkFixture(
            name="smoke",
            assignment_id="benchmark-assignment-smoke",
            assessment_context=_ASSESSMENT_CONTEXT,
            anchors=_ANCHORS[:4],
            essays=_ESSAYS[:4],
        )

    return BenchmarkFixture(
        name="full",
        assignment_id="benchmark-assignment-full",
        assessment_context=_ASSESSMENT_CONTEXT,
        anchors=_ANCHORS[:10],
        essays=_ESSAYS[:10],
    )
