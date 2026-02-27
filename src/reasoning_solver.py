# -*- coding: utf-8 -*-
"""
推理求解模块：读取 extracted_tasks.json，按题 has_image 决定是否带图调用推理模型，
生成教辅级 solved_answers.json（含 solution_process, knowledge_points, alternative_methods, extensions）。
"""
import json
from pathlib import Path

from .api_client import APIClient
from .pdf_processor import get_output_base, load_chapter_config


REASONING_SYSTEM = """你是一名学术造诣深厚且教学经验丰富的大学理科教授，负责编写“教辅级”参考答案。
你的教学风格是**严谨、形式化、推导详尽且注重物理直觉（如果是物理相关的题目）**。
你的答案应该用中文回答，若有硬核的专业术语可在括号内写出英文。

**身份与核心原则：**
1.  **拒绝科普化比喻**：不要使用科普式的比喻。请直接使用相关的专业术语。
2.  **数学推导优先**：解答必须展示完整的逻辑链条。不要直接给出结果（如“易得”、“显然”），除非是极为基础的代数运算。要拒绝防御性证明（即在证明过程中有意或无意仅保留了验证证明正确性的最少信息，从而隐藏自己的证明思路和解决问题的方法的目的）
3.  **物理图像结合**：建立方程时，必须解释每一项的物理来源；在得到结果后，简要分析结果的物理意义。


输出格式：严格输出一个 JSON 对象，且只输出该对象，不要 markdown 代码块。包含以下键：
- solution_process: 解答过程的 LaTeX 源码（不要使用 \\usepackage，不要输出 \\begin{document}）。
- knowledge_points: 本题涉及的基础知识点总结（纯文本或简单 LaTeX 列表）。
- alternative_methods: 如果有一题多解，请详细写出并对这些方法进行总结（如不同方法的优缺点，体现了哪些不同看问题的角度）。你不必总是在这个部分输出内容，不必将本质完全相同或相似的方法牵强地说成是“一题多解”，你可以大胆输出空字符串 ""。
- extensions: 如果有值得积累和记忆的二级结论，请务必列出，帮助学生积累（这里的“二级结论”是一些超出课程考核本身基础要求的高级引理或高阶拓展，往往能够简化题目的求解，或提供更高的视角来看待这个问题）。你不必总是输出这个内容，不必将基础知识视作“二级结论”，不必牵强地为一些没有高等背景的题生成“二级结论”部分，你可以大胆地输出空字符串 ""。

JSON 中 LaTeX 的转义规则（必须遵守，否则会出现 rac、heta 等乱码）：
- 在 JSON 字符串里，单个反斜杠 \\f 会被解析成换页符、\\t 会变成制表符，导致 \\frac、\\theta 等被破坏。
- 所有 LaTeX 反斜杠必须写成双反斜杠，例如：\\\\frac{1}{2}、\\\\theta、\\\\alpha、\\\\beta、\\\\begin{equation}、\\\\end{equation}、\\\\textbf{注：...}。这样解析后才能得到正确的 \\frac、\\theta。
- 换行请用真实换行，不要写 \\n，不要写 \\n！！！

禁止 Markdown：禁止使用 **加粗**星号、# 标题、1. 2. 列表。加粗一律用 \\\\textbf{...}，列表用 \\\\begin{itemize} \\\\item ... \\\\end{itemize}。

LaTeX 规范（防冲突与排版）：
- 使用 \\\\label{} 时必须带题号前缀，例如 \\\\label{eq:2-1-1}。
- 不要使用任何 \\usepackage，不要输出 \\begin{document}。
- 行内数学必须放在 $...$ 中：例如 $\\\\mathcal{E}$、$\\\\nabla \\\\cdot \\\\mathbf{E}$、$\\\\neq$、$\\\\ref{eq:2-1-1}$。禁止在文字中单独写 \\\\mathcal、\\\\mathbf、\\\\nabla、\\\\ref、\\\\neq 等而不加 $，否则会报 “allowed only in math mode” 或 “Missing $ inserted”。

优雅降级：若题目引用了正文公式（如“证明式 3.16”）而你没有正文上下文，请基于专业知识推断最可能的公式进行解答，并在答案开头用 \\\\textbf{注：本解答假设式 3.16 为 [你推断的公式]。} 注明。"""


def _fix_json_control_chars(s: str) -> str:
    """将 JSON 字符串值内的未转义控制字符转为合法转义，避免 Invalid control character。"""
    result = []
    i = 0
    in_string = False
    escape_next = False
    while i < len(s):
        c = s[i]
        if escape_next:
            result.append(c)
            escape_next = False
            i += 1
            continue
        if c == "\\" and in_string:
            result.append(c)
            escape_next = True
            i += 1
            continue
        if c == '"':
            result.append(c)
            in_string = not in_string
            i += 1
            continue
        if in_string and ord(c) < 32:
            if c == "\n":
                result.append("\\n")
            elif c == "\r":
                result.append("\\r")
            elif c == "\t":
                result.append("\\t")
            else:
                result.append(f"\\u{ord(c):04x}")
            i += 1
            continue
        result.append(c)
        i += 1
    return "".join(result)


def _fix_json_invalid_escapes(s: str) -> str:
    """修复 JSON 中非法反斜杠（如 LaTeX），使 json.loads 能解析。"""
    result = []
    i = 0
    while i < len(s):
        if s[i] == "\\" and i + 1 < len(s):
            n = s[i + 1]
            if n in '"\\/bfnrt':
                result.append(s[i : i + 2])
                i += 2
                continue
            if n == "u" and i + 5 <= len(s):
                hex_part = s[i + 2 : i + 6]
                if len(hex_part) == 4 and all(c in "0123456789abcdefABCDEF" for c in hex_part):
                    result.append(s[i : i + 6])
                    i += 6
                    continue
            result.append("\\\\")
            result.append(n)
            i += 2
            continue
        result.append(s[i])
        i += 1
    return "".join(result)


def _extract_json_object(text: str) -> dict:
    """从模型输出中解析单个 JSON 对象。"""
    text = text.strip()
    for start in ("```json", "```"):
        if text.startswith(start):
            text = text[len(start):].strip()
        if text.endswith("```"):
            text = text[:-3].strip()
    start_idx = text.find("{")
    if start_idx == -1:
        raise ValueError("未找到 JSON 对象")
    depth = 0
    end_idx = -1
    for i in range(start_idx, len(text)):
        if text[i] == "{":
            depth += 1
        elif text[i] == "}":
            depth -= 1
            if depth == 0:
                end_idx = i + 1
                break
    if end_idx == -1:
        raise ValueError("JSON 对象未闭合")
    segment = _fix_json_invalid_escapes(text[start_idx:end_idx])
    segment = _fix_json_control_chars(segment)
    return json.loads(segment)


def solve_one_task(
    client: APIClient,
    task: dict,
    root_dir: str | Path,
    model: str | None = None,
) -> dict:
    """
    解答单道题。若 has_image 为 true 则附带 image_path 对应图片。
    返回符合 solved_answers 单条格式的 dict。
    """
    root_dir = Path(root_dir)
    qid = task.get("question_id", "")
    content = task.get("content", "")
    has_image = task.get("has_image", False)
    image_path = task.get("image_path", "")

    base_user = (
        f"题目编号：{qid}\n【题目内容】\n{content}\n\n"
        "请按教辅标准给出解答（JSON 格式，含 solution_process, knowledge_points, alternative_methods, extensions）。"
    )

    def _call(u: str) -> str:
        if has_image and image_path:
            full_path = root_dir / image_path
            if full_path.exists():
                return client.chat(
                    [{"role": "system", "content": REASONING_SYSTEM}, {"role": "user", "content": u}],
                    image_path=str(full_path),
                    model=model,
                )
        return client.chat(
            [{"role": "system", "content": REASONING_SYSTEM}, {"role": "user", "content": u}],
            model=model,
        )

    raw = _call(base_user)
    try:
        obj = _extract_json_object(raw)
    except Exception:
        # 常见原因：输出过长被截断导致 JSON 未闭合；或模型夹杂了额外文本导致解析失败。
        # 处理：请求模型重新输出一份“更短但完整”的 JSON（字段必须齐全），通常能显著降低截断概率。
        retry_user = (
            base_user
            + "\n\n【重要】你刚才的输出可能被截断或 JSON 未闭合。请重新输出一个更短但仍完整的 JSON 对象：\n"
            "- 必须只输出 JSON 对象（以 { 开头，以 } 结尾），不得输出任何解释。\n"
            "- solution_process 请压缩篇幅：保留关键推导步骤与最终结论即可。\n"
            "- alternative_methods/extensions 若没有就输出空字符串 \"\"。\n"
            "- 确保所有括号/引号闭合。\n"
        )
        raw = _call(retry_user)
        obj = _extract_json_object(raw)

    return {
        "question_id": qid,
        "solution_process": obj.get("solution_process", ""),
        "knowledge_points": obj.get("knowledge_points", ""),
        "alternative_methods": obj.get("alternative_methods", ""),
        "extensions": obj.get("extensions", ""),
    }


def run(
    extracted_path: str | Path | None = None,
    output_path: str | Path | None = None,
    root_dir: str | Path | None = None,
    output_base: str | Path | None = None,
    config_path: str | Path | None = None,
    provider: str = "gemini",
    model: str | None = None,
) -> list[dict]:
    """
    读取 extracted_tasks.json，逐题求解，写入 solved_answers.json。
    若未传 output_base，则根据 config_path 的 book_title 得到 output/<book_title>。
    """
    root = Path(__file__).resolve().parent.parent
    root_dir = root_dir or root
    config_path = config_path or root / "input" / "chapter_config.json"
    if output_base is None:
        output_base = get_output_base(root, config_path)
    output_base = Path(output_base)
    extracted_path = extracted_path or (output_base / "extracted_tasks.json")
    output_path = output_path or (output_base / "solved_answers.json")

    with open(extracted_path, "r", encoding="utf-8") as f:
        tasks = json.load(f)
    if not tasks:
        raise ValueError("extracted_tasks.json 为空")

    # 断点续传：已存在的 solved_answers.json 中已有题不再重复求解，按 extracted 顺序合并
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    if Path(output_path).exists():
        with open(output_path, "r", encoding="utf-8") as f:
            existing_list = json.load(f)
        ans_by_id = {a["question_id"]: a for a in existing_list}
    else:
        ans_by_id = {}

    client = APIClient(provider=provider)
    task_ids: list[str] = [t.get("question_id", "") for t in tasks]

    def _ordered_answers() -> list[dict]:
        # 关键：每次写盘都按 extracted_tasks.json 的顺序写“全量已存在答案”，
        # 避免中途写盘时把文件截断成“前缀”，从而导致后续题目被迫重跑。
        return [ans_by_id[qid] for qid in task_ids if qid in ans_by_id]

    for task in tasks:
        qid = task.get("question_id", "")
        if not qid:
            continue
        if qid in ans_by_id:
            continue
        try:
            ans_by_id[qid] = solve_one_task(client, task, root_dir, model=model)
        except Exception as e:
            ans_by_id[qid] = {
                "question_id": qid,
                "solution_process": f"[解答生成失败: {e}]",
                "knowledge_points": "",
                "alternative_methods": "",
                "extensions": "",
            }
        # 每解完一题立即写回（全量），便于断点续传且不丢后面的已有答案
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(_ordered_answers(), f, ensure_ascii=False, indent=2)

    return _ordered_answers()
