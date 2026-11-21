'''Quy tắc đánh dấu "cần đơn vị có thẩm quyền xác nhận" (Pipeline mục 4.1: "Kém" ở QĐ 3266 và
"Yếu" ở QĐ 4932 không được tự đồng nhất). Tách khỏi main.py để test được mà không cần FastAPI.
TV1 bổ sung quy tắc khi phát hiện thêm.'''
import re

# (các từ khóa phải có đủ, ít nhất một trong các từ khóa còn lại)
VERIFY_RULES = [(('rèn luyện',), ('kém', 'yếu'))]

# Diễn đạt tắt không nhắc "rèn luyện" (ca CTU-085: "bị Yếu"): chỉ khớp khi "yếu/kém" đứng ngay sau
# từ chỉ xếp loại, để không dính "chủ yếu", "yếu tố", "kém" trong ngữ cảnh khác.
LOW_GRADE = re.compile(r'(?<!\w)(?:bị|loại|mức|xếp loại|xếp hạng)\s+(?:rèn luyện\s+)?(?:yếu|kém)(?!\w)')


def needs_verification(question: str) -> bool:
    q = question.lower()
    if any(all(a in q for a in must) and any(b in q for b in any_of) for must, any_of in VERIFY_RULES):
        return True
    return bool(LOW_GRADE.search(q))
