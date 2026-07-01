import os
import sys
import unittest

# 프로젝트 루트 경로 확보
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from src.app.utils import mask_name

class TestMaskName(unittest.TestCase):
    """utils.py의 mask_name 개인정보 마스킹 로직을 검증하는 단위 테스트 스위트"""

    def test_mask_name_edge_cases(self):
        # 1. Null 및 빈 문자열 검증
        self.assertEqual(mask_name(None), "")
        self.assertEqual(mask_name(""), "")
        self.assertEqual(mask_name("   "), "")

        # 2. 1글자 이름 검증 (영문 외자 및 한글 외자)
        self.assertEqual(mask_name("A"), "A")
        self.assertEqual(mask_name("홍"), "홍")

        # 3. 2글자 이름 검증 (첫 글자만 노출하고 두 번째 글자 마스킹)
        self.assertEqual(mask_name("홍길"), "홍*")
        self.assertEqual(mask_name("Bo"), "B*")
        self.assertEqual(mask_name("Ed"), "E*")

        # 4. 3글자 이름 검증 (가운데 마스킹)
        self.assertEqual(mask_name("홍길동"), "홍*동")
        self.assertEqual(mask_name("Kim"), "K*m")

        # 5. 4글자 이상 긴 한글 이름 검증
        self.assertEqual(mask_name("제임스허"), "제**허")
        self.assertEqual(mask_name("남궁길동"), "남**동")

        # 6. 공백을 포함한 긴 영문명 단어별 마스킹 검증 (John Doe -> J**n D*e)
        self.assertEqual(mask_name("John Doe"), "J**n D*e")
        self.assertEqual(mask_name("Hong Gil Dong"), "H**g G*l D**g")
        self.assertEqual(mask_name("A B C"), "A B C")  # 외자 단어들의 연속 조합

if __name__ == "__main__":
    unittest.main()
