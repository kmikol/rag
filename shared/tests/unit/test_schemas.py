import pytest
from pydantic import ValidationError

from shared.schemas import ChatResponse


def test_chat_response_accepts_answered_state() -> None:
    response = ChatResponse(
        answer="Grounded answer [1].",
        citations=[],
        refused=False,
    )

    assert response.refused is False


def test_chat_response_accepts_refused_state() -> None:
    response = ChatResponse(
        answer=None,
        citations=[],
        refused=True,
        refusal_reason="Retrieved evidence is insufficient to answer reliably.",
    )

    assert response.refused is True


@pytest.mark.parametrize(
    ("answer", "refused", "refusal_reason"),
    [
        (None, False, None),
        ("", False, None),
        ("Grounded answer [1].", False, "Should not be present."),
        ("Grounded answer [1].", True, "Should not include an answer."),
        (None, True, None),
        (None, True, ""),
    ],
)
def test_chat_response_rejects_inconsistent_states(
    answer: str | None,
    refused: bool,
    refusal_reason: str | None,
) -> None:
    with pytest.raises(ValidationError):
        ChatResponse(
            answer=answer,
            citations=[],
            refused=refused,
            refusal_reason=refusal_reason,
        )
