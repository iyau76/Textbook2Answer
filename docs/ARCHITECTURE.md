# 架构设计文档 — Textbook2Answer

**版本**: v2.0（P1+P2+P3 重构后）  
**更新日期**: 2026年3月10日

---

## 目录

1. [系统概览](#系统概览)
2. [目录结构](#目录结构)
3. [核心模块说明](#核心模块说明)
4. [数据流与阶段说明](#数据流与阶段说明)
5. [关键设计决策](#关键设计决策)
6. [扩展点](#扩展点)

---

## 系统概览

```
教材 PDF
   │
   ▼ Phase 1: pdf_processor
   页面图片 (output/<book>/images/page_N.png)
   │
   ▼ Phase 2: vlm_extractor  [VLM: Gemini 等]
   习题 JSON (extracted_tasks.json)
   │
   ▼ Phase 3: reasoning_solver  [推理模型: DeepSeek 等]
   解答 JSON (solved_answers.json)
   │
   ▼ Phase 4: latex_builder  [Jinja2 模板]
   .tex 文件 → 用户本地 xelatex 编译 → PDF
```

主流程由 `Pipeline` 统一编排，对外暴露事件回调接口供 CLI/GUI/API 均可使用。

---

## 目录结构

```
Textbook2Answer/
├── main.py               # CLI 入口（通过 argparse 调用 Pipeline）
├── requirements.txt
├── .gitignore
│
├── src/                  # 核心业务代码
│   ├── __init__.py
│   ├── pipeline.py       # 流水线编排 + 事件系统（GUI 集成核心）
│   ├── api_client.py     # 多模态 LLM/VLM API 客户端
│   ├── pdf_processor.py  # PDF → PNG 切片
│   ├── vlm_extractor.py  # VLM 提取习题 JSON
│   ├── reasoning_solver.py  # 推理模型生成解答
│   ├── latex_builder.py  # LaTeX 清洗 + Jinja2 渲染
│   ├── logger.py         # 统一日志（支持 GUI 回调 handler）
│   ├── constants.py      # 全局常量
│   ├── utils.py          # 工具类（CheckpointManager 等）
│   └── config_schema.py  # 配置格式校验
│
├── config/
│   ├── api_config.json         # 真实密钥（.gitignore 忽略）
│   └── api_config.example.json # 示例模板
│
├── input/
│   ├── chapter_config.json     # 书本与章节页码配置
│   └── textbook.pdf            # 教材 PDF（.gitignore 忽略）
│
├── output/                     # 全部运行产物（.gitignore 忽略）
│   └── <book_title>/
│       ├── images/             # PDF 页面 PNG
│       ├── extracted_tasks.json
│       ├── solved_answers.json
│       ├── solve_failures.json # 失败题目汇总（如有）
│       ├── final_solution.tex
│       └── run.log
│
├── templates/
│   └── main_template.tex       # Jinja2 LaTeX 模板
│
├── tests/
│   ├── test_gemini_api.py
│   ├── test_latex_cleaner.py
│   ├── test_json_fix.py
│   ├── test_json_repro.py
│   ├── test_math_regex.py
│   ├── test_runner.py
│   └── fixtures/
│
├── scripts/
│   └── fix_cache_data.py       # 缓存修复脚本
│
└── docs/
    ├── ARCHITECTURE.md         # 本文件
    ├── API.md                  # 编程接口文档
    ├── GUI_MIGRATION.md        # GUI 升级计划
    ├── TROUBLESHOOTING.md      # 故障排查
    └── PROJECT_AUDIT.md        # 历史审计报告
```

---

## 核心模块说明

### `src/pipeline.py` — 流水线编排核心

项目编排中枢。所有代码入口（CLI、GUI、API）最终应通过 `Pipeline` 运行，而非直接调用各模块 `run()`。

```python
class PipelineConfig:          # 纯数据类，描述一次运行参数
class PipelineEvent:           # 结构化事件（类型/阶段/进度/耗时/附加数据）
class Pipeline:
    run_pdf()                  # Phase 1
    run_extract()              # Phase 2
    run_solve()                # Phase 3
    run_latex() -> Path        # Phase 4
    run() -> Path              # 全量一键运行
    output_paths               # 各输出路径字典（@property）
    completed_stages           # 已完成阶段列表（@property，供 UI 初始化）
```

### `src/api_client.py` — API 客户端

支持 **Gemini REST API** 和 **OpenAI 兼容接口**（DeepSeek、自定义节点）。

- `_load_config()`: 双路径查找（`config/api_config.json` → `api_config.json`）
- `_merge_image_sources()`: 路径与 base64 合并去重（防止重复图片）
- `chat()`: 统一出口，自动 dispatch 到 `_chat_gemini()` 或 `_chat_openai_compatible()`

### `src/vlm_extractor.py` — VLM 习题提取

- 按章节分批调用 VLM，传入页面图片列表
- 输出符合 schema 的 `extracted_tasks.json`
- 内置断点续传：已提取章节自动跳过

### `src/reasoning_solver.py` — 推理求解

- 每题独立调用推理模型，生成 `solution_process + knowledge_points + ...`
- JSON 解析失败自动重试（最多 `MAX_SOLVE_JSON_RETRIES` 次）
- 每题完成立即写盘（全量），断点续传
- 失败题目写入 `solve_failures.json`，方便针对性重跑

### `src/latex_builder.py` — LaTeX 组装

- `_clean_latex_text()` / `_norm()`：模块级函数，LaTeX 清洗（转义修复、案例修复等）
- 合并 `extracted_tasks.json` + `solved_answers.json`，渲染 Jinja2 模板

### `src/logger.py` — 统一日志

```python
logger                        # 模块级 Logger 实例
setup_log_file(path)          # 添加 FileHandler（每次运行一个日志文件）
add_ui_handler(callback)      # 注册 GUI 回调 handler
remove_ui_handlers()          # 清除 GUI handler（页面刷新时调用）
```

---

## 数据流与阶段说明

### Phase 1 — PDF 切片

**输入**: `input/textbook.pdf` + `input/chapter_config.json`（读取页码范围）  
**输出**: `output/<book>/images/page_N.png`  
**断点**: 已存在的 PNG 不重新渲染

### Phase 2 — VLM 提取

**输入**: `images/` 目录 + chapter_config 章节信息  
**输出**: `extracted_tasks.json`（字段：`chapter_name, question_id, content, has_image, page_num, image_path`）  
**断点**: 已提取章节（基于 `done_pages` 集合）自动跳过

### Phase 3 — 推理求解

**输入**: `extracted_tasks.json`  
**输出**: `solved_answers.json`（字段：`question_id, solution_process, knowledge_points, alternative_methods, extensions`）  
**断点**: `ans_by_id` 字典持久化，`[解答生成失败` 开头的条目触发重跑

### Phase 4 — LaTeX 组装

**输入**: `extracted_tasks.json` + `solved_answers.json` + `templates/main_template.tex` + `chapter_config.json`（book_title）  
**输出**: `final_solution.tex`（用 `xelatex` 编译得到 PDF）

---

## 关键设计决策

### 1. 全量写盘而非增量追加

`reasoning_solver.py` 每题完成后写整个 `solved_answers.json`（全量），而非 append。目的是：
- 保持文件始终可合法解析（中途不产生损坏的 JSON）
- 按 `extracted_tasks.json` 顺序重排，保证输出顺序稳定

### 2. 双路径 api_config 查找

`api_client._load_config()` 先查 `config/api_config.json`，再查根目录 `api_config.json`。向后兼容旧版本，同时支持新目录结构。

### 3. 嵌套函数移出模块级

`latex_builder._clean_latex_text()` 和 `_norm()` 已从 `build_chapters()` 内部移到模块级，便于：
- 在 `tests/test_latex_cleaner.py` 中单独测试
- 未来在其他模块复用清洗逻辑

---

## 扩展点

| 需求 | 扩展位置 |
|------|---------|
| 添加新 API 提供商 | `api_client.py` — 新增 `_chat_xxx()` 分支 |
| 修改习题提取 Prompt | `vlm_extractor.py` — `EXTRACT_SYSTEM` 常量 |
| 修改解答格式/风格 | `reasoning_solver.py` — `SOLVE_SYSTEM` 常量 |
| 修改 LaTeX 排版 | `templates/main_template.tex` |
| 添加 GUI | `gui/streamlit_app.py`（见 GUI_MIGRATION.md） |
| 校验配置 | `src/config_schema.py` — `validate_*` 函数 |
| 修改日志格式 | `src/logger.py` — `get_logger()` 中的 Formatter |
