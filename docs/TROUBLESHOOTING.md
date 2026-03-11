# 故障排查指南 — Textbook2Answer

---

## 目录

1. [配置问题](#配置问题)
2. [Phase 1 — PDF 切片](#phase-1--pdf-切片)
3. [Phase 2 — VLM 提取](#phase-2--vlm-提取)
4. [Phase 3 — 推理求解](#phase-3--推理求解)
5. [Phase 4 — LaTeX 编译](#phase-4--latex-编译)
6. [API 连接问题](#api-连接问题)
7. [性能与资源](#性能与资源)

---

## 配置问题

### `FileNotFoundError: api_config.json`

程序按以下顺序查找配置文件：
1. `config/api_config.json`
2. `api_config.json`（根目录）

**解决**：将 `config/api_config.example.json` 复制为 `config/api_config.json`，填入真实 API Key。

```bash
cp config/api_config.example.json config/api_config.json
# 然后编辑 config/api_config.json，填入 api_key
```

### `配置校验失败: 节点 [xxx] 缺少必填字段 'api_key'`

运行配置校验工具确认问题：

```bash
python -m src.config_schema
# 或指定路径
python -m src.config_schema --api config/api_config.json --chapter input/chapter_config.json
```

### `ValueError: chapter_config 中未配置任何页码`

`input/chapter_config.json` 中 `chapters` 数组为空，或每个章节的 `pages` 为空列表。

**示例正确格式**：
```json
{
  "book_title": "量子力学",
  "chapters": [
    {
      "chapter_name": "第一章 波函数",
      "pages": [45, 46, 47, 48]
    }
  ]
}
```

---

## Phase 1 — PDF 切片

### `没有生成任何 PNG 文件`

- 检查 `input/textbook.pdf` 是否存在
- 检查 `chapter_config.json` 中的页码是否在 PDF 总页数范围内（PDF 页码从 1 开始）
- 若 PDF 受密码保护，PyMuPDF 无法渲染，需先解锁

### `输出图片质量差 / 分辨率太低`

在 `src/pdf_processor.py` 中提高渲染 DPI 参数（默认通常为 150dpi）：

```python
# 找到 render_pdf_pages 函数中的 matrix 参数，提高倍率
mat = fitz.Matrix(2, 2)  # 2x 放大，约 144dpi → 288dpi
```

---

## Phase 2 — VLM 提取

### `提取结果为空 / 题目数量异常少`

1. 检查发送给 VLM 的图片路径是否有效
2. 检查 `output/<book>/images/` 目录下是否有对应章节的 PNG 文件
3. 在日志中观察 VLM 的原始响应（`DEBUG` 级别日志写在 `run.log` 中）

### `JSONDecodeError: 模型输出无法解析为 JSON`

- VLM 可能在响应中混入了 Markdown 代码块（`\`\`\`json ... \`\`\``），代码内含有处理逻辑
- 检查 `_clean_json_string()` 和 `_extract_json_array()` 是否能处理该模型的输出格式
- 临时方案：重新运行（断点续传会自动跳过已提取章节）

### `某章节被跳过（明明未提取）`

断点续传策略：**只要该章任意一页出现在 `done_pages` 集合中，整章跳过**。

如需重新提取某章：
1. 打开 `output/<book>/extracted_tasks.json`，删除该章的所有条目
2. 重新运行 `--skip-pdf` 即可

---

## Phase 3 — 推理求解

### `大量题目出现 [解答生成失败: ...]`

1. 查看 `output/<book>/solve_failures.json`，了解失败原因分类
2. 常见原因：API 超时（增大 `timeout_seconds`）、余额不足、网络不稳
3. 直接重新运行：程序会检测到 `[解答生成失败` 前缀并自动重跑这些题目

### `某题一直卡死`

- 提高 `api_config.json` 中 `timeout_seconds`（建议推理模型设 240+）
- 若某题持续失败，可手动在 `solved_answers.json` 中删除该题目条目

### `solved_answers.json 顺序乱了`

这是正常现象，因为断点续传时跳过+补充会改变顺序。`latex_builder` 在组装时会按 `extracted_tasks.json` 的顺序重排，最终 LaTeX 顺序是正确的。

---

## Phase 4 — LaTeX 编译

### `xelatex 编译报错 "allowed only in math mode"`

某题的数学符号（如 `\mathcal{E}`）未被包含在 `$...$` 中。
- 检查 `extracted_tasks.json` 中对应题目的 `content` 字段
- 或检查 `solved_answers.json` 中错误题目的 `solution_process`

**临时修复**：手动编辑 JSON 文件中的 LaTeX 语法。  
**根本解决**：在 `vlm_extractor.py` 的 `EXTRACT_SYSTEM` Prompt 中强化约束（已有示例）。

### `字体缺失：CJK 字符无法显示`

```
LaTeX error: Package fontspec Error: The font "XXX" cannot be found.
```

**解决**：安装中文字体，或修改 `templates/main_template.tex` 中的字体配置：
```latex
\setCJKmainfont{SimSun}  % Windows
% 或
\setCJKmainfont{Noto Serif CJK SC}  % Linux/macOS
```

### `\begin{cases} 编译报错`

`_clean_latex_text()` 已处理大多数 cases 问题，若仍有报错：
- 确认公式环境包裹正确：`cases` 必须在 `$...$` 或 `\[...\]` 内部
- 检查 `cases` 内部行分隔符是否为 `\\` 而非单个 `\n`

---

## API 连接问题

### `requests.exceptions.Timeout`

增大 `api_config.json` 中 `timeout_seconds` 值。推理模型建议至少 240 秒：
```json
"deepseek": {
  "timeout_seconds": 300,
  "max_retries": 2,
  "retry_backoff_seconds": 5
}
```

### `401 Unauthorized`

API Key 无效或已过期，更新 `config/api_config.json` 中的 `api_key`。

### `429 Too Many Requests`

触发速率限制：
- 增大 `retry_backoff_seconds`（等待时间）
- 减少并发（目前串行处理，若有并发需降低）

### `Gemini 返回空 candidates`

Gemini 安全过滤导致响应为空。
- 检查题目内容是否触发 Gemini 安全策略
- 尝试改写 Prompt，避免可能被误判的关键词
- 或换用 OpenAI 兼容节点处理该书

---

## 性能与资源

### 整本书处理太慢

- **提取阶段**：Gemini Flash 速度最快，推荐大批量提取
- **求解阶段**：推理模型（DeepSeek Reasoner）每题约 30-120 秒属正常
- 利用断点续传，可分批次、多次运行（随时 Ctrl+C 中断，下次继续）

### 日志文件

运行日志保存在 `output/<book_title>/run.log`，包含 DEBUG 级别完整日志，适合排查复杂问题：

```bash
# 查看最后 100 行
tail -n 100 output/量子力学/run.log

# 只看 ERROR/WARNING
grep -E "ERROR|WARNING" output/量子力学/run.log
```

### 磁盘空间

图片目录可能占用较多空间（每页约 100-500KB）：
```bash
du -sh output/*/images/
```

完成后可手动删除 `images/` 目录，只保留 JSON 和 .tex 文件。
