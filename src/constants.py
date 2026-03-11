# -*- coding: utf-8 -*-
"""
项目全局常量。集中管理 magic string，避免散落在各模块中。
"""

# ---- API 默认配置 ------------------------------------------------
DEFAULT_PROVIDER: str = "gemini"
DEFAULT_TIMEOUT_SECONDS: int = 120
DEFAULT_MAX_RETRIES: int = 2
DEFAULT_TEMPERATURE: float = 0.2

# ---- 求解模块 ----------------------------------------------------
# solve_one_task 中 JSON 解析失败后，最多再额外重试几次（不含首次请求）
MAX_SOLVE_JSON_RETRIES: int = 2

# 识别"上次求解失败"的标记前缀（写入 solved_answers.json 中）
FAILURE_PREFIX: str = "[解答生成失败"

# ---- JSON schema 字段名 ------------------------------------------
F_CHAPTER_NAME = "chapter_name"
F_QUESTION_ID = "question_id"
F_CONTENT = "content"
F_HAS_IMAGE = "has_image"
F_PAGE_NUM = "page_num"
F_IMAGE_PATH = "image_path"
F_SOLUTION_PROCESS = "solution_process"
F_KNOWLEDGE_POINTS = "knowledge_points"
F_ALTERNATIVE_METHODS = "alternative_methods"
F_EXTENSIONS = "extensions"

# ---- 输出文件名 --------------------------------------------------
EXTRACTED_TASKS_FILE = "extracted_tasks.json"
SOLVED_ANSWERS_FILE = "solved_answers.json"
SOLVE_FAILURES_FILE = "solve_failures.json"
FINAL_SOLUTION_FILE = "final_solution.tex"
