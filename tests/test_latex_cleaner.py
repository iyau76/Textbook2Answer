# -*- coding: utf-8 -*-
"""
测试 latex_builder.py 中的 _clean_latex_text 是否能正确清洗大模型的不合规输出
"""

import sys
import os
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# 通过内部引入方式获取该函数进行单元测试
from src.latex_builder import _clean_latex_text


class TestLatexCleaner(unittest.TestCase):
    cleaner = staticmethod(_clean_latex_text)

    def test_api_error_message(self):
        """测试清理 API 报错信息中的下划线"""
        raw = "这里有一个错误：[解答生成失败: HTTPSConnectionPool(host='api.gemini.com', port=443)]"
        expected = r"这里有一个错误：[解答生成失败: HTTPSConnectionPool(host='api.gemini.com', port=443)]"
        self.assertEqual(self.cleaner(raw), expected.replace("_", "\\_"))

    def test_redundant_slashes(self):
        """测试去除多余的斜杠，如 \\\\textbf 和 \\\\begin"""
        raw = r"这里应该加粗 \\\\textbf{加粗文本} 然后换行 \\\\ 然后 \\\\begin{equation} x=1 \\\\end{equation}"
        expected = r"这里应该加粗 \textbf{加粗文本} 然后换行 \\ 然后 \begin{equation} x=1 \end{equation}"
        self.assertEqual(self.cleaner(raw), expected)

    def test_missing_math_slashes(self):
        """测试孤立特殊字符被转义，如 %, &, _ (不在数学环境中)"""
        # _在纯文本中会被转义，而在 $$ 或 \[\] 中不被转义
        raw = r"这是一个测试_文本，含有100%的几率，且A & B。数学公式 $a_1 = b_2$ 不受影响。 \begin{equation} x_{ij} = % 错误但保留 \end{equation}"
        # 预期的文本部分
        result = self.cleaner(raw)
        self.assertIn(r"测试\_文本", result)
        self.assertIn(r"100\%", result)
        self.assertIn(r"A \& B", result)
        # 公式部分应该保持不变
        self.assertIn(r"$a_1 = b_2$", result)

    def test_literal_newline(self):
        """测试模型错误的输出了 \\n 或者 \n，应纠正为真正的换行"""
        raw = r"文字1\\n文字2\n文字3"
        expected = "文字1\n文字2\n文字3"
        self.assertEqual(self.cleaner(raw), expected)

    def test_frac_missing_slash(self):
        """测试模型漏写了 frac 的反斜杠"""
        # 注意因为 frac 前边没有斜杠，会被补上
        raw = r"结果是 frac{1}{2}"
        expected = r"结果是 \frac{1}{2}"
        self.assertEqual(self.cleaner(raw), expected)

    def test_cases_missing_newline_slashes(self):
        """测试 cases 环境缺少 \\ 结尾"""
        raw = r"""\begin{cases}
x = 1
y = 2
\end{cases}"""
        result = self.cleaner(raw)
        # 应该变成了带 \\ 的形式
        self.assertIn(r"\\", result)
        self.assertIn("x = 1", result)

if __name__ == '__main__':
    unittest.main()
