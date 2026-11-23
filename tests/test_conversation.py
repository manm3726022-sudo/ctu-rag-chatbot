from backend.schemas import ChatTurn
from backend.services.conversation import (
    contextualize_question,
    is_confirmation_followup,
)


def test_standalone_question_ignores_completed_conversation():
    history = [
        ChatTurn(role='user', content='Một học kỳ tối đa bao nhiêu tín chỉ?'),
        ChatTurn(role='assistant', content='Tối đa 20 tín chỉ [S1].'),
    ]

    assert contextualize_question('Điều kiện rút học phần là gì?', history) == (
        'Điều kiện rút học phần là gì?'
    )


def test_followup_after_clarification_keeps_original_question():
    history = [
        ChatTurn(role='user', content='Điều kiện cảnh báo học vụ là gì?'),
        ChatTurn(
            role='assistant',
            content='Bạn thuộc khóa tuyển sinh nào?',
            need_clarification=True,
        ),
    ]

    resolved = contextualize_question('Khóa 47', history)
    assert 'Điều kiện cảnh báo học vụ là gì?' in resolved
    assert 'Bạn thuộc khóa tuyển sinh nào?' in resolved
    assert 'Khóa 47' in resolved


def test_multiple_clarifications_keep_all_answers_since_last_completed_turn():
    history = [
        ChatTurn(role='user', content='Quy định này áp dụng cho trường hợp nào?'),
        ChatTurn(
            role='assistant',
            content='Bạn hỏi học kỳ nào?',
            need_clarification=True,
        ),
        ChatTurn(role='user', content='HK1 năm học 2026-2027'),
        ChatTurn(
            role='assistant',
            content='Bạn học chương trình nào?',
            need_clarification=True,
        ),
    ]

    resolved = contextualize_question('Đại học chính quy', history)
    assert 'Quy định này áp dụng cho trường hợp nào?' in resolved
    assert 'HK1 năm học 2026-2027' in resolved
    assert 'Đại học chính quy' in resolved


def test_affirmative_to_paraphrase_reuses_original_without_repeating_confirmation():
    history = [
        ChatTurn(
            role='user',
            content='3.7 điểm trên thang điểm 4 có tương ứng với điểm A không?',
        ),
        ChatTurn(
            role='assistant',
            content='Bạn muốn biết điểm 3.7 tương ứng với điểm chữ nào? Vui lòng xác nhận.',
            need_clarification=True,
        ),
    ]

    assert is_confirmation_followup('Đúng vậy', history)
    resolved = contextualize_question('Đúng vậy', history)
    assert '3.7 điểm trên thang điểm 4 có tương ứng với điểm A không?' in resolved
    assert 'không hỏi xác nhận lại' in resolved
