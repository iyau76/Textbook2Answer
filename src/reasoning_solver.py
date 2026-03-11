# -*- coding: utf-8 -*-
"""
推理求解模块：读取 extracted_tasks.json，按题 has_image 决定是否带图调用推理模型，
生成教辅级 solved_answers.json（含 solution_process, knowledge_points, alternative_methods, extensions）。
"""
import json
import time
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from .api_client import APIClient
from .pdf_processor import get_output_base, load_chapter_config
from .logger import logger
from .constants import FAILURE_PREFIX, SOLVED_ANSWERS_FILE, SOLVE_FAILURES_FILE


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

JSON 中关于 LaTeX 的编写规则：
- 建议你使用原生的 LaTeX 语法进行公式表达即可，例如：\\frac{1}{2}、\\theta、\\alpha、\\begin{equation}、\\end{equation} 等等。不要试图使用四条斜杠 `\\\\`，直接按照写 LaTeX 源码的直觉来即可。
- 对于换行，你可以使用字面量的回车换行，不需要在字符串里硬写 `\\n` 这种控制字符。

禁止 Markdown：禁止使用 **加粗**星号、# 标题、1. 2. 列表。加粗一律用 \\textbf{...}，列表用 \\begin{itemize} \\item ... \\end{itemize}。

LaTeX 规范（防冲突与排版）：
- 使用 \\label{} 时必须带题号前缀，例如 \\label{eq:2-1-1}。
- 不要使用任何 \\usepackage，不要输出 \\begin{document}。
- 行内数学必须放在 $...$ 中：例如 $\\mathcal{E}$、$\\nabla \\cdot \\mathbf{E}$、$\\neq$、$\\ref{eq:2-1-1}$。禁止在文字中单独写 \\mathcal、\\mathbf、\\nabla、\\ref、\\neq 等而不加 $，否则会报 “allowed only in math mode” 或 “Missing $ inserted”。

优雅降级：若题目引用了正文公式（如“证明式 3.16”）而你没有正文上下文，请基于专业知识推断最可能的公式进行解答，并在答案开头用 \\textbf{注：本解答假设式 3.16 为 [你推断的公式] 且继续。} 注明。"""

REASONING_SYSTEM_EN = """You are a university professor with deep academic expertise and rich teaching experience, responsible for writing "textbook-level" reference solutions.
Your teaching style is **rigorous, formal, detailed in derivations, and emphasizes physical intuition (for physics-related problems)**.
Answer in English. For specialized terminology, you can provide Chinese translations in parentheses if appropriate.

**Identity and Core Principles:**
1. **Avoid popularization analogies**: Do not use science journalism-style metaphors. Use professional terminology directly.
2. **Mathematical derivations first**: Answers must show complete logical chains. Do not directly give results (e.g., "obviously", "it follows") unless they are basic algebraic manipulations. Avoid defensive proofs.
3. **Physical intuition combined**: When establishing equations, explain the physical origin of each term; after obtaining results, briefly analyze the physical meaning.

**Output Format**: Strictly output a single JSON object only, without markdown code blocks. Include the following keys:
- solution_process: LaTeX source code of the solution process (do not use \\usepackage, do not output \\begin{document}).
- knowledge_points: Summary of basic knowledge points involved in this problem (plain text or simple LaTeX lists).
- alternative_methods: If there are multiple solution methods, provide them in detail and summarize these approaches. You don't need to always output this section, and you can boldly output an empty string "".
- extensions: If there are worth-remembering second-level conclusions, list them to help students accumulate knowledge. You can boldly output an empty string if not applicable.

**LaTeX Rules in JSON:**
- Use native LaTeX syntax for formulas, e.g., \\frac{1}{2}, \\theta, \\alpha, \\begin{equation}, \\end{equation}.
- For line breaks, use literal newlines, do not write control characters like `\\n`.

**Forbidden Markdown**: No **bold** asterisks, # headers, numbered lists. Use \\textbf{...} for bold and \\begin{itemize} \\item ... \\end{itemize} for lists.

**LaTeX Standards:**
- When using \\label{}, include the problem number prefix, e.g., \\label{eq:2-1-1}.
- Do not use any \\usepackage, do not output \\begin{document}.
- Inline math must be in $...$ delimiters.

**Graceful Degradation**: If the problem references equations from the main text (e.g., "prove equation 3.16") and you lack context, infer the most likely equation based on professional knowledge and note at the beginning."""


def get_reasoning_system_prompt(language: str = "zh") -> str:
    """获取推理系统提示词（支持多语言）。
    
    Args:
        language: 语言代码，'zh' 为中文，'en' 为英文。
    
    Returns:
        对应语言的系统提示词。
    """
    if language == "en":
        return REASONING_SYSTEM_EN
    return REASONING_SYSTEM

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
    import re
    return re.sub(r'(?<!\\)\\(?!["\\/u])', r'\\\\', s)


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
    except Exception as first_err:
        logger.warning("题目 %s 首次 JSON 解析失败（%s），发起重试...", qid, type(first_err).__name__)
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
    max_workers: int = 1,
) -> list[dict]:
    """
    读取 extracted_tasks.json，逐题求解，写入 solved_answers.json。
    若未传 output_base，则根据 config_path 的 book_title 得到 output/<book_title>。
    max_workers > 1 时使用线程池并发求解以加速。
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
    total = len(task_ids)
    done_count = len(ans_by_id)
    logger.info("共 %d 题，已有缓存 %d 题，待求解 %d 题", total, done_count, total - done_count)

    # 用锁保护 ans_by_id 和写盘操作，确保并发安全
    _lock = threading.Lock()

    def _ordered_answers() -> list[dict]:
        return [ans_by_id[qid] for qid in task_ids if qid in ans_by_id]

    def _flush():
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(_ordered_answers(), f, ensure_ascii=False, indent=2)

    # 筛选待求解的题目
    pending_tasks = []
    for idx, task in enumerate(tasks):
        qid = task.get("question_id", "")
        if not qid:
            continue
        if qid in ans_by_id:
            existing_ans = ans_by_id[qid].get("solution_process", "")
            if FAILURE_PREFIX in existing_ans:
                logger.info("题目 %s: 检测到上次失败记录，将重新生成", qid)
                with _lock:
                    ans_by_id.pop(qid, None)
            else:
                continue
        pending_tasks.append((idx, task))

    solved_in_session = 0
    effective_workers = min(max(max_workers, 1), len(pending_tasks) or 1)

    def _solve_one(idx_task):
        idx, task = idx_task
        qid = task.get("question_id", "")
        logger.info("求解 [%d/%d] 题目 %s ...", idx + 1, total, qid)
        try:
            result = solve_one_task(client, task, root_dir, model=model)
        except Exception as e:
            logger.error("题目 %s 求解失败: %s", qid, e)
            result = {
                "question_id": qid,
                "solution_process": f"[解答生成失败: {e}]",
                "knowledge_points": "",
                "alternative_methods": "",
                "extensions": "",
            }
        with _lock:
            ans_by_id[qid] = result
            _flush()
        return qid, FAILURE_PREFIX not in result.get("solution_process", "")

    if effective_workers <= 1:
        # 串行模式
        for idx_task in pending_tasks:
            qid, ok = _solve_one(idx_task)
            if ok:
                solved_in_session += 1
    else:
        logger.info("使用 %d 个线程并发求解", effective_workers)
        with ThreadPoolExecutor(max_workers=effective_workers) as pool:
            futures = {pool.submit(_solve_one, it): it for it in pending_tasks}
            for future in as_completed(futures):
                qid, ok = future.result()
                if ok:
                    solved_in_session += 1

    # 汇总失败题目，写入单独文件
    all_answers = _ordered_answers()
    failed = [a for a in all_answers if a.get("solution_process", "").startswith(FAILURE_PREFIX)]
    if failed:
        fail_path = output_base / SOLVE_FAILURES_FILE
        with open(fail_path, "w", encoding="utf-8") as f:
            json.dump(
                [{"question_id": a["question_id"], "reason": a["solution_process"]} for a in failed],
                f, ensure_ascii=False, indent=2,
            )
        logger.warning("本次共 %d 题求解失败，详见 %s", len(failed), fail_path)
    else:
        logger.info("本次所有题目求解成功（本次新增 %d 题）", solved_in_session)

    return all_answers
