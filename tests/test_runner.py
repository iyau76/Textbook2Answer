import re

def _clean_latex_text(s: str) -> str:
    if not s:
        return ""
    
    # 1. 修复由于模型抛出的带下划线的错误信息导致编译失败的问题
    s = re.sub(r"\[解答生成失败.*?\]", lambda m: m.group(0).replace("_", "\\_"), s)

    # 2. 修复误写的字面量 \\n 和 \n
    s = s.replace("\\\\n", "\n").replace("\\n", "\n")

    # 3. 修复过度的转义（如 \\\\textbf -> \\textbf）
    # 优先替换常见的命令
    for cmd in ["textbf", "begin", "end", "item", "frac", "label", "ref", "cite", "mathbb", "mathcal"]:
        s = s.replace(f"\\\\\\\\{cmd}", f"\\{cmd}")
    # 处理遗留的 \\\\ -> \\
    s = s.replace("\\\\\\\\", "\\\\")

    # 4. 修复漏转义的正文保留字：_、%、&
    # 将文本切分为数学环境和非数学环境
    math_pattern = r"(\$\$.*?\$\$|\$.*?\$|\\\[.*?\\\]|\\begin\{equation\}.*?\\end\{equation\}|\\begin\{align\*?\}.*?\\end\{align\*?\}|\\begin\{cases\}.*?\\end\{cases\})"
    parts = re.split(math_pattern, s, flags=re.DOTALL)
    
    for i in range(len(parts)):
        if i % 2 == 0:
            # 这是非数学模式（纯文本区域）
            text = parts[i]
            # 加前视断言防止重复转义
            text = re.sub(r"(?<!\\)_", r"\_", text)
            text = re.sub(r"(?<!\\)%", r"\%", text)
            text = re.sub(r"(?<!\\)&", r"\&", text)
            parts[i] = text

    s = "".join(parts)
    
    # 5. 修复特例：在 cases/aligned 等环境中缺少的 \\ （模型偶尔漏掉）
    def fix_cases(m):
        inner = m.group(1)
        if "\\\\" not in inner and "\n" in inner.strip():
            inner = inner.replace("\n", "\\\\\n")
        return f"\\begin{{cases}}{inner}\\end{{cases}}"
    
    s = re.sub(r"\\begin\{cases\}(.*?)\\end\{cases\}", fix_cases, s, flags=re.DOTALL)
    
    # 6. 顺手牵羊：修复某些漏掉反斜杠的 frac 
    s = re.sub(r"(?<!\\)frac\{", r"\\frac{", s)

    return s


print("==============================")
print("TEST 1: API Error [解答生成失败...]")
raw = "这里有一个错误：[解答生成失败: HTTPSConnectionPool(host='api.gemini.com', port=443_2)]"
print("Raw :", raw)
print("Out :", _clean_latex_text(raw))
print("==============================")

print("TEST 2: Redundant Slashes")
raw = r"这里应该加粗 \\\\textbf{加粗文本} 然后换行 \\\\ 然后 \\\\begin{equation} x=1 \\\\end{equation}"
print("Raw :", raw)
print("Out :", _clean_latex_text(raw))
print("==============================")

print("TEST 3: Missing Math Slashes (%, &, _)")
raw = r"这是一个测试_文本，含有100%的几率，且A & B。数学公式 $a_1 = b_2$ 不受影响。 \begin{equation} x_{ij} = % 错误但保留 \end{equation}"
print("Raw :", raw)
print("Out :", _clean_latex_text(raw))
print("==============================")

print("TEST 4: Literal Newline")
raw = r"文字1\\n文字2\n文字3"
print("Raw :", raw)
print("Out :", _clean_latex_text(raw))
print("==============================")

print("TEST 5: Frac missing slash")
raw = r"结果是 frac{1}{2} 而且不应该替换 \\frac"
print("Raw :", raw)
print("Out :", _clean_latex_text(raw))
print("==============================")

print("TEST 6: Cases missing newline")
raw = r"""\begin{cases}
x = 1
y = 2
\end{cases}"""
print("Raw :", raw)
print("Out :", _clean_latex_text(raw))
print("==============================")

print("ALL TESTS RUN.")
