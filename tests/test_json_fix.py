import json
import re

def _clean_json_string(s: str) -> str:
    """清理并修复大模型输出的 JSON 字符串，使其符合标准 JSON 格式。"""
    if not s:
        return s
    
    start_idx = s.find('{')
    arr_start_idx = s.find('[')
    if start_idx == -1 and arr_start_idx == -1:
        return s
    start = start_idx if arr_start_idx == -1 else (arr_start_idx if start_idx == -1 else min(start_idx, arr_start_idx))
    
    end_idx = s.rfind('}')
    arr_end_idx = s.rfind(']')
    end = end_idx if arr_end_idx == -1 else (arr_end_idx if end_idx == -1 else max(end_idx, arr_end_idx))
    
    if end < start:
        return s
        
    json_str = s[start:end+1]
    
    # NEW REGEX: only exclude " \ / u
    json_str = re.sub(r'(?<!\\)\\(?!["\\/u])', r'\\\\', json_str)
    
    result = []
    in_string = False
    escape_next = False
    
    for i, c in enumerate(json_str):
        if escape_next:
            result.append(c)
            escape_next = False
            continue
        if c == '\\':
            result.append(c)
            escape_next = True
            continue
        if c == '"':
            in_string = not in_string
            result.append(c)
            continue
        if in_string:
            if c == '\n':
                result.append('\\n')
            elif c == '\r':
                result.append('\\r')
            elif c == '\t':
                result.append('\\t')
            elif ord(c) < 32:
                result.append(f"\\u{ord(c):04x}")
            else:
                result.append(c)
        else:
            result.append(c)
            
    return "".join(result)


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
    
    # 4.1 UNESCAPE labels and refs
    def unescape_labels(m):
        return m.group(0).replace(r"\_", "_")
    
    s = re.sub(r"\\(label|ref|eqref|cite)\{.*?\}", unescape_labels, s)

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

# Test JSON
raw_json = r"""
{
    "solution_process": "\begin{equation} \bar{x} = \frac{1}{2} \right] \nabla \end{equation}",
    "knowledge_points": "Some \n text \b \f \r \t",
    "extensions": "Line1\nLine2"
}
"""

print("Original JSON:\n" + repr(raw_json))
cleaned_json = _clean_json_string(raw_json)
print("Cleaned JSON string:\n" + repr(cleaned_json))

try:
    data = json.loads(cleaned_json)
    print("Parsed JSON object:", data)
    
    latex = data["solution_process"]
    print("LaTeX before clean latex text:", repr(latex))
    print("LaTeX after clean latex text:", repr(_clean_latex_text(latex)))
except Exception as e:
    print("JSON Parse Error:", e)

# Test label unescape
raw_latex = r"Here is a reference \ref{eq:my_label_1} and \label{sec:intro_1}. $x_1$ and text_1."
print("Label unescape test:")
print(raw_latex)
print(_clean_latex_text(raw_latex))

