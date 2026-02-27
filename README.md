# Textbook2Answer（教辅级参考答案生成系统）

将大学理工科教材 PDF **自动转化**为“教辅级” LaTeX 参考答案文档：

- 手工指定章节与 PDF 物理页码；
- VLM 从教材页面中**提取习题**；
- 推理模型生成**教辅级解答 + 知识点 + 一题多解 + 二级结论**；
- 使用 LaTeX/Jinja2 生成 **可编译的 .tex**（再由你本地编译为 PDF）。

## 目录

- 环境与安装
- 配置文件
  - `api_config.json`（模型与 API 配置）
  - `input/chapter_config.json`（书本与章节配置）
- 命令行参数总览
- 典型运行方式
- 断点续传机制
- 输出结构
- LaTeX 与模型行为约定
- 常见配置示例

## 环境与安装

- **Python**：3.10+
- **依赖安装**：

```bash
pip install -r requirements.txt
# requirements.txt 中包含：
# - PyMuPDF
# - requests
# - Jinja2
```

## 配置文件

### `api_config.json`（模型与 API 配置）

位于项目根目录，用来配置所有可用的模型节点，例如：

```json
{
  "deepseek": {
    "base_url": "https://ark.cn-beijing.volces.com/api/v3",
    "api_key": "YOUR_DEEPSEEK_KEY",
    "model": "deepseek-v3-2-251201",
    "timeout_seconds": 240,
    "max_retries": 2,
    "retry_backoff_seconds": 2,
    "temperature": 0.2,
    "max_tokens": 4096
  },
  "gemini": {
    "base_url": "https://generativelanguage.googleapis.com/v1beta/",
    "api_key": "YOUR_GEMINI_KEY",
    "model": "gemini-3-flash-preview",
    "timeout_seconds": 120,
    "max_retries": 1,
    "retry_backoff_seconds": 2,
    "temperature": 0.2,
    "max_tokens": 2048
  },
  "custom1": {
    "base_url": "https://api.gemai.cc/v1/chat/completions",
    "api_key": "YOUR_CUSTOM_KEY",
    "model": "gpt-5.2"
  }
}
```

**字段说明**：

- **`base_url`**（必填）  
  - 对 Gemini：一般为 `https://generativelanguage.googleapis.com/v1beta/`  
  - 对 OpenAI 兼容节点（DeepSeek 等）：  
    - 可以是根路径，如 `https://ark.cn-beijing.volces.com/api/v3`  
    - 也可以是完整的 `.../chat/completions` endpoint（代码已兼容两种写法）。

- **`api_key`**（必填）  
  该节点对应的密钥。

- **`model`**（推荐填写）  
  默认的模型名称，如 `deepseek-v3-2-251201`、`gemini-3-flash-preview`。

- **`timeout_seconds`**（可选，默认 120）  
  单次请求的超时时间（秒）。  
  DeepSeek 等“慢推理”模型建议设置到 `240` 或 `300`。

- **`max_retries`**（可选，默认 2）  
  当遇到 **超时 / 429 / 5xx** 时的自动重试次数。

- **`retry_backoff_seconds`**（可选，默认 2.0）  
  重试退避基数（指数退避）：第 n 次重试前会 `sleep(backoff * 2^n)` 秒。

- **`temperature`**（可选，默认 0.2）  
  控制输出随机性；解析稳定性优先时建议偏小（0.0–0.3）。

- **`max_tokens`**（可选）  
  - 对 OpenAI 兼容节点会映射成 `max_tokens`；  
  - 对 Gemini 会映射为 `maxOutputTokens`。  
  太小：答案可能被截断；太大：更容易超时 / 成本高。建议从 2048 / 4096 起步，根据需要调整。

你可以随意增加节点（如 `"gpt41"`、`"gpt5"`、`"custom2"`），运行时通过命令行参数选择要用哪个节点。

### `input/chapter_config.json`（书本与章节配置）

为每本书配一份，决定：

- 输出目录名（`book_title`）
- 标题页作者信息（`author_model`）
- 教材 PDF 路径（`pdf_path`）
- 章节与 PDF 物理页码映射。

示例：

```json
{
  "book_title": "量子力学",
  "author_model": "deepseek-v3-2-251201",
  "pdf_path": "input/量子力学教材.pdf",
  "chapters": [
    {
      "chapter_name": "第一章 量子力学的历史渊源",
      "pages": [15]
    },
    {
      "chapter_name": "第二章 波函数与 Schrödinger 方程",
      "pages": [21, 27]
    }
  ]
}
```

**字段说明**：

- **`book_title`**  
  - 用于生成输出目录：`output/<book_title>/`  
  - 程序会自动替换路径非法字符（`\ / : * ? " < > |` 和空白）为下划线。

- **`author_model`**  
  写入 LaTeX 标题页的作者字段（非真实作者，仅展示用，如使用的模型名）。

- **`pdf_path`**（可选）  
  教材 PDF 路径，可以是 **相对路径**（相对项目根目录）或 **绝对路径**。  
  若未设置，则由命令行 `--pdf` 或默认 `input/textbook.pdf` 决定。

- **`chapters`**（数组）  
  每个元素：
  - `chapter_name`：章节名（写入 `\section{}` 和目录）
  - `pages`：PDF 物理页码列表（从 1 开始），需要人工确定哪些页是该章节的习题页。

## 命令行参数总览

基础调用：

```bash
python main.py [options]
```

### 流程控制

- **`--skip-pdf`**  
  跳过 PDF 切片步骤（`pdf_processor`），直接使用已存在的 `output/<book>/images/`。

- **`--skip-extract`**  
  跳过 VLM 提取步骤（`vlm_extractor`），直接使用已有 `output/<book>/extracted_tasks.json`。

- **`--skip-solve`**  
  跳过推理求解步骤（`reasoning_solver`），直接使用已存在 `output/<book>/solved_answers.json`。

- **`--only-latex`**  
  只执行 LaTeX 组装步骤（`latex_builder`），仅用当前 JSON 生成 `final_solution.tex`。

### 配置与路径

- **`--config PATH`**  
  指定 `chapter_config.json` 路径（默认 `input/chapter_config.json`）。

- **`--pdf PATH`**  
  指定教材 PDF 路径（优先级最高）。  
  优先级为：  
  1. 命令行 `--pdf`  
  2. `chapter_config.json` 里的 `pdf_path`  
  3. 默认 `input/textbook.pdf`

### 模型与 API 选择

- **`--provider NAME`**  
  全局默认 API 节点名（兼容旧用法），如 `gemini`、`deepseek`、`custom1`。  
  若未单独指定 `--extract-provider/--solve-provider`，则两者都使用该节点。

- **`--extract-provider NAME`**  
  VLM 提取阶段使用的节点名。  
  例如：`--extract-provider gemini`。

- **`--solve-provider NAME`**  
  推理求解阶段使用的节点名。  
  例如：`--solve-provider deepseek`、`--solve-provider custom1`。

- **`--extract-model MODEL_NAME`**（可选）  
  覆盖提取阶段的模型名；不指定则使用相应节点的 `model`。

- **`--solve-model MODEL_NAME`**（可选）  
  覆盖解答阶段的模型名；不指定则使用相应节点的 `model`。

## 典型运行方式

### 全流程（切片 + 提取 + 解答 + LaTeX）

```bash
python main.py
```

### 仅重新生成 LaTeX（不重新调用模型）

```bash
python main.py --only-latex
```

### 只重跑解答（保留已有提取）

```bash
python main.py --skip-pdf --skip-extract
```

### Gemini 提取 + DeepSeek 解答

```bash
python main.py --extract-provider gemini --solve-provider deepseek
```

### 使用自定义节点 `custom1` 解答

```bash
python main.py --extract-provider gemini --solve-provider custom1 --solve-model gpt-5.2
```

## 断点续传机制

本项目的断点续传分为两段：提取与解答，均实时写盘。

### 提取阶段（按页）—— `output/<book>/extracted_tasks.json`

- **跳过策略**：  
  读取 `extracted_tasks.json` 中的所有 `page_num`，视为已完成的页码。再次运行时，这些页码会被跳过，不再调用 VLM。

- **写盘策略**：  
  每完成一页，立即把“已有记录 + 新页记录”写回 `extracted_tasks.json`。

> 若想重提取某一页，请删除该页所有 `page_num=该页` 的记录，或直接删除整份 `extracted_tasks.json` 后重跑提取。

### 解答阶段（按题）—— `output/<book>/solved_answers.json`

- **跳过策略**：  
  若 `solved_answers.json` 存在，则读取其中的 `question_id` 集合，视为已完成的题号。再次运行时仅对缺失的题号求解。

- **写盘策略**：  
  每解完一题，就按 `extracted_tasks.json` 中题目的顺序写回**全量答案**，不会把文件“截断成前缀”。

**推荐的“删一题后重跑”流程**：

1. 在 `output/<book>/solved_answers.json` 中删除对应 `question_id` 的对象；
2. 运行：

```bash
python main.py --skip-pdf --skip-extract
```

程序只会补回缺失的题，不会重复跑其它题。

## 输出结构

以 `book_title: "量子力学"` 为例：

```text
output/
  量子力学/
    images/
      page_15.png
      page_21.png
      ...
    extracted_tasks.json
    solved_answers.json
    final_solution.tex
```

- `images/`：`pdf_processor` 渲染的指定页 PNG。
- `extracted_tasks.json`：VLM 提取到的题目列表（包含 `chapter_name`、`question_id`、`content`、`has_image`、`page_num`、`image_path`）。
- `solved_answers.json`：推理模型产出的教辅级解答。
- `final_solution.tex`：完整 LaTeX 源码，你需本地用 `xelatex` 等编译为 PDF。

## LaTeX 与模型行为约定

为保证 `.tex` 能稳定编译，对模型输出做了如下约定（通过 Prompt + 清洗代码实现）：

- **禁止输出导言区**：  
  不允许输出 `\usepackage`、`\documentclass`、`\begin{document}` 等，它们统一由模板负责。

- **标签命名隔离**：  
  所有 `\label{}` 必须以题号为前缀，例如 `\label{eq:2-1-1}`。

- **数学模式要求**：  
  - 行内数学必须写在 `$...$` 中：  
    如 `$\\mathcal{E}$`、`$\\nabla \\cdot \\mathbf{E}$`、`$\\neq$`、`$\\ref{eq:2-1-1}$`。  
  - 不允许在正文中裸写 `\mathcal`、`\mathbf`、`\nabla`、`\ref`、`\neq` 等而不加 `$`。  
  - `cases` 环境、`\infty` 等明显“只能在数学模式中”的结构，会在提取阶段做一次保守修正（如自动包成 `\[\begin{cases}...\end{cases}\]` 或 `$\\infty$`），以降低编译失败概率。

- **JSON + LaTeX 转义**：  
  - JSON 字符串中，单反斜杠 `\f`、`\t` 会被当成控制字符，所以 LaTeX 命令需用双反斜杠：`\\frac`、`\\theta`、`\\alpha`、`\\begin{equation}` 等。  
  - 解析前，代码会对常见非法转义做修复，并对控制字符做安全转义。

## 常见配置示例

### 使用 Gemini 全流程

```bash
python main.py --provider gemini
```

### Gemini 提取 + DeepSeek 解答

```bash
python main.py --extract-provider gemini --solve-provider deepseek
```

并在 `deepseek` 节点设置更大的 `timeout_seconds` 与合适的 `max_tokens`。

### 使用自定义 OpenAI 兼容模型

```bash
python main.py \
  --extract-provider gemini \
  --solve-provider custom1 \
  --solve-model gpt-5.2
```

## 测试

```bash
python tests/test_gemini_api.py   # 测试 Gemini 文本与图片接口（文本 + 图片）
```

更多设计细节与 Prompt 约定可参考项目内的《Textbook2Answer开发说明文档.md》。

# Textbook2Answer（教辅级参考答案生成系统）

将大学理工科教材 PDF 自动转化为“教辅级” LaTeX 参考答案文档。

## 环境

- Python 3.10+
- 依赖：`pip install -r requirements.txt`（PyMuPDF、requests、Jinja2）

## 配置

1. **API**：在项目根目录的 `api_config.json` 中配置模型（当前优先使用 `gemini` 节点）。
2. **输入**：
   - 编辑 `input/chapter_config.json`，填写书名、模型名及章节与 PDF 页码映射。
   - 教材 PDF 路径可以用命令行 `--pdf` 指定，也可以写入 `chapter_config.json` 的 `pdf_path` 字段（见下文）。

### `chapter_config.json` 格式（示例）

```json
{
  "book_title": "量子光学",
  "author_model": "gemini-3-flash-preview",
  "pdf_path": "input/量子光学教材.pdf",
  "chapters": [
    {
      "chapter_name": "第二章 经典电磁学",
      "pages": [43, 44]
    }
  ]
}
```

- `book_title`：用于输出目录命名（会自动清理非法路径字符）。
- `author_model`：写入 LaTeX 标题页作者处（纯展示用）。
- `pdf_path`（可选）：教材 PDF 路径。可写相对路径（相对项目根目录）或绝对路径。
- `chapters[].pages`：PDF **物理页码**（从 1 开始），由你人工指定。

## 使用

```bash
# 全流程：PDF 切片 -> VLM 提取 -> 推理求解 -> LaTeX 组装
python main.py

# 仅生成 LaTeX（已有 extracted_tasks.json 与 solved_answers.json 时）
python main.py --only-latex

# 跳过某几步
python main.py --skip-pdf --skip-extract   # 只做求解 + LaTeX
python main.py --skip-solve                 # 只做 PDF + 提取 + LaTeX
```
### 指定教材 PDF 路径

- **命令行指定**（优先级最高）：

```bash
python main.py --pdf "D:/Books/量子光学第2版.pdf"
```

- **配置文件指定**：在 `chapter_config.json` 写 `pdf_path`，然后直接 `python main.py`。

优先级：`--pdf` > `chapter_config.json:pdf_path` > `input/textbook.pdf`（兜底）。

### 指定“提取模型 / 解答模型”

你可以分别指定“题目提取用哪个 API 节点、题目解答用哪个 API 节点”，例如用 Gemini 做提取、用 DeepSeek 做解答：

```bash
python main.py --extract-provider gemini --solve-provider deepseek
```

也可以在同一个 API 节点上临时覆盖 model 名称（可选）：

```bash
python main.py --extract-provider gemini --extract-model gemini-3-flash-preview --solve-provider deepseek --solve-model deepseek-v3-2-251201
```

说明：
- `--provider` 仍保留作默认值（兼容旧用法），若不传 `--extract-provider/--solve-provider` 则两者都使用 `--provider`。
- `api_config.json` 里你可以自定义节点名，例如 `"custom1": {...}`，运行时直接 `--solve-provider custom1` 即可。

### DeepSeek/自定义节点的超时与重试（重要）

当使用 DeepSeek（或其它 OpenAI 兼容节点）时，若遇到：
- `Read timed out`：通常是推理时间长/网络抖动；
- `JSON 对象未闭合`：通常是输出过长被截断（或夹杂了多余文本）。

建议在 `api_config.json` 的对应节点里加入这些可选字段（不会影响其它节点）：

```json
{
  "deepseek": {
    "base_url": "https://ark.cn-beijing.volces.com/api/v3",
    "api_key": "...",
    "model": "deepseek-v3-2-251201",
    "timeout_seconds": 300,
    "max_retries": 2,
    "retry_backoff_seconds": 2,
    "temperature": 0.2,
    "max_tokens": 4096
  }
}
```

说明：
- `timeout_seconds`：单次请求超时（默认 120），推理慢时建议 300 或更高。
- `max_retries`/`retry_backoff_seconds`：超时/429/5xx 会自动重试并指数退避。
- `max_tokens`：限制/控制输出长度，避免过长被截断；如果你需要更长解答，可以适当调大。

代码层面也做了兜底：若解答 JSON 解析失败，会自动要求模型“重新输出更短但完整的 JSON”，以降低截断概率。

## 断点续传（当前实现）

断点续传分两段：**提取（按页）**与**求解（按题）**，并且两者都是“实时写盘”。若中途中断，再次运行同一本书（同一 `output/<book_title>/`）时会自动跳过已完成部分，只处理未完成部分。

### 1）VLM 提取断点（`output/<book>/extracted_tasks.json`）

- **跳过策略**：如果 `extracted_tasks.json` 已存在，会读取其中所有记录的 `page_num`，把这些页视为“已完成”，后续运行会跳过这些页，不再调用 VLM。
- **写盘策略**：每处理完一页，会把“已有结果 + 新页结果”写回 `extracted_tasks.json`。

注意：如果你只删除了该页中的“某一道题”，但仍保留了该页的其它题，那么该页的 `page_num` 仍存在，程序会认为该页已经完成，不会重提取。若要重提取某页，请删除该页所有 `page_num=该页` 的记录（或直接删掉整份 `extracted_tasks.json` 重新提取）。

### 2）推理求解断点（`output/<book>/solved_answers.json`）

- **跳过策略**：如果 `solved_answers.json` 已存在，会读取其中的 `question_id` 集合；再次运行时只会对“缺失的题号”调用模型求解。
- **写盘策略（重要）**：每解完一题会把**全量已存在答案（按 extracted_tasks 的题目顺序）**写回 `solved_answers.json`，不会把文件截断成“前缀”。

#### 手动删掉某题答案后重跑（你希望的工作流）

1. 打开 `output/<book_title>/solved_answers.json`，删除对应 `question_id` 的那条对象。
2. 重新运行（不重提取/不重切片）：

```bash
python main.py --skip-pdf --skip-extract
```

程序会只重跑缺失的题，不会重复跑其它题。

## 输出

按 `chapter_config.json` 中的 `book_title` 分目录存放，便于多本书管理：

- `output/<book_title>/images/`：PDF 页面 PNG
- `output/<book_title>/extracted_tasks.json`：VLM 提取的习题
- `output/<book_title>/solved_answers.json`：推理模型生成的解答
- `output/<book_title>/final_solution.tex`：最终 LaTeX 源码（需本地用 xelatex 等编译为 PDF）

书名中的非法路径字符会替换为下划线。

## 常见问题（排错要点）

- **“\\mathcal allowed only in math mode / Missing $ inserted”**：题干或答案里出现了 `\\mathcal`、`\\mathbf`、`\\nabla`、`\\neq` 等但没有放进 `$...$` 或 `\\[...\\]`。
- **出现 `rac` / `heta` / `ef` / ` abla` 等**：通常是 JSON 转义或错误的字符串替换导致（例如把 `\\n` 当换行替换）。当前代码已避免在组装阶段替换 `\\n/\\r`，并在提示词中要求 JSON 内 LaTeX 使用双反斜杠。

## 测试

```bash
python tests/test_gemini_api.py   # 测试 Gemini 文本与图片接口
```

详见《Textbook2Answer开发说明文档.md》。

## 下一步改进与优化方向（建议路线）

- **更稳定的结构化输出**：给 VLM/推理模型加更严格的 JSON Schema（或用 Pydantic 校验 + 自动重试），减少解析失败。
- **“按题重跑/按页重跑”开关**：增加命令行参数，例如 `--redo-pages 43,44`、`--redo-questions 2.1,2.3`，避免手工编辑 JSON。
- **LaTeX 清洗器**：在写入 `.tex` 前做安全过滤/修复（例如自动把明显的 `\\mathcal` 行内包上 `$...$` 的保守修复、移除 Markdown 残留等）。
- **编译自愈（可选）**：可加一个“编译-读 log-自动修复”的循环（速度慢但更自动化）。
- **引用上下文（RAG）**：遇到“如式 3.16 / 类比习题 2-18”时检索正文/已解题库补全上下文。
- **GUI**：把页码配置做成图形界面，并加入任务队列与进度/失败重试。
