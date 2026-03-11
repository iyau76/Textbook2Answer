# Textbook2Answer（教辅级参考答案生成系统）

Textbook2Answer 用于将教材 PDF 自动转换为可编译的 LaTeX 参考答案。

核心流程：

1. PDF 切片（渲染题目页图片）
2. VLM 提取题目（生成 extracted_tasks.json）
3. 推理模型解答（生成 solved_answers.json）
4. LaTeX 组装（生成 final_solution.tex）

本项目同时支持：

- 命令行（CLI）
- Web 图形界面（Streamlit）

---

## 1. 项目文档

| 文档 | 说明 |
|------|------|
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | 架构与模块设计 |
| [docs/INTEGRATION_GUIDE.md](docs/INTEGRATION_GUIDE.md) | 新功能集成指南（API配置、多语言、任务队列） |
| [docs/TROUBLESHOOTING.md](docs/TROUBLESHOOTING.md) | 故障排查 |
| [docs/USER_GUIDE.md](docs/USER_GUIDE.md) | 详细操作手册（GUI + CLI） |
| [docs/QUICK_REFERENCE.md](docs/QUICK_REFERENCE.md) | 快速参考 |

---

## 2. 环境与安装

- Python 3.10+
- 推荐 Windows PowerShell / macOS Terminal / Linux Bash

安装依赖：

```bash
pip install -r requirements.txt
```

当前 requirements 包含：

- PyMuPDF
- requests
- Jinja2
- streamlit（Web GUI 使用）

---

## 3. 快速开始（最短路径）

### 第一步：准备 API 配置

将示例复制为实际配置文件：

```bash
cp config/api_config.example.json config/api_config.json
```

然后编辑 [config/api_config.json](config/api_config.json) 填入真实 API Key。

说明：程序按以下顺序查找 API 配置：

1. config/api_config.json
2. 根目录 api_config.json（兼容旧版本）

### 第二步：准备章节配置

你有两种方式：

1. GUI 向导自动生成（推荐）
2. 手动编辑 [input/chapter_config.json](input/chapter_config.json)

手动编辑至少填写：

- book_title
- chapters[].chapter_name
- chapters[].pages
- 可选 pdf_path

可先校验配置：

```bash
python -m src.config_schema
```

### 第三步：运行

CLI 全流程：

```bash
python main.py
```

或启动 Web GUI：

```bash
streamlit run gui/streamlit_app.py
```

---

## 4. 运行方式

### 4.1 CLI 运行

基础：

```bash
python main.py [options]
```

常用参数：

- --skip-pdf：跳过 PDF 切片
- --skip-extract：跳过 VLM 提取
- --skip-solve：跳过推理解答
- --only-latex：仅组装 LaTeX
- --config PATH：指定 chapter_config.json
- --pdf PATH：指定教材 PDF（优先级最高）
- --provider NAME：默认 API 节点
- --extract-provider NAME：提取阶段节点
- --solve-provider NAME：求解阶段节点
- --extract-model MODEL：覆盖提取模型
- --solve-model MODEL：覆盖解答模型

示例：

```bash
# 只重跑解答 + LaTeX
python main.py --skip-pdf --skip-extract

# Gemini 提取 + DeepSeek 解答
python main.py --extract-provider gemini --solve-provider deepseek

# 仅组装 LaTeX
python main.py --only-latex
```

### 4.2 Web GUI 运行

启动：

```bash
streamlit run gui/streamlit_app.py
```

**GUI 支持功能**：

#### 系统设置（侧边栏）
- 🌍 **多语言支持** - 中文/英文界面随时切换
- 🔑 **API配置管理** - 可视化配置VLM和LLM，支持6大预设供应商（Gemini, DeepSeek, Qwen, Claude, Zhipu, OpenAI）和自定义API
- 📋 **任务队列管理** - 查看、暂停、恢复、取消后台任务

#### 主要标签页
- 🧭 **新建项目向导** - 书名、PDF、章节页码、质量档位一站式配置
- 📁 **项目中心** - 项目列表、配置校验、统计信息、批量管理
- 🚀 **任务中心** - 全流程/局部运行、失败题重跑、实时日志
- 🧪 **审阅与修订** - 题目与答案在线修改、一键重跑
- 📦 **导出与报告** - LaTeX 下载、版本快照、运行报告

详细操作请看 [docs/USER_GUIDE.md](docs/USER_GUIDE.md)。
新功能集成指南详见 [docs/INTEGRATION_GUIDE.md](docs/INTEGRATION_GUIDE.md)。

---

## 5. 配置文件说明

### 5.1 API 配置：config/api_config.json

示例（节选）：

```json
{
  "gemini": {
    "provider": "gemini",
    "api_key": "YOUR_GEMINI_API_KEY",
    "model": "gemini-2.5-flash-preview-05-20",
    "base_url": "https://generativelanguage.googleapis.com/v1beta"
  },
  "deepseek": {
    "provider": "openai_compatible",
    "api_key": "YOUR_DEEPSEEK_API_KEY",
    "model": "deepseek-reasoner",
    "base_url": "https://api.deepseek.com/v1"
  }
}
```

推荐可选字段：

- timeout_seconds
- max_retries
- retry_backoff_seconds
- temperature
- max_tokens

### 5.2 章节配置：input/chapter_config.json

示例：

```json
{
  "book_title": "量子力学",
  "author_model": "deepseek-reasoner",
  "pdf_path": "input/量子力学教材.pdf",
  "chapters": [
    {
      "chapter_name": "第一章",
      "pages": [15, 16, 17]
    }
  ]
}
```

字段说明：

- book_title：输出目录名（output/<book_title>/）
- author_model：写入 LaTeX 标题页展示
- pdf_path：可选，支持相对或绝对路径
- chapters[].pages：PDF 物理页码（从 1 开始）

---

## 6. 断点续传与重跑

### 提取阶段

文件：[output/<book>/extracted_tasks.json](output)

- 已提取页码会自动跳过
- 每阶段持续写盘，中断后可续跑

### 求解阶段

文件：[output/<book>/solved_answers.json](output)

- 已存在 question_id 自动跳过
- 失败题会记录到 solve_failures.json
- 再次运行会自动重试失败题（基于失败前缀识别）

### 典型只补跑缺失题

1. 删除 solved_answers.json 中对应 question_id
2. 执行：

```bash
python main.py --skip-pdf --skip-extract
```

---

## 7. 输出结构

```text
output/
  <book_title>/
    images/
    extracted_tasks.json
    solved_answers.json
    solve_failures.json   # 如有失败题
    final_solution.tex
    run.log
```

说明：

- final_solution.tex 需你本地用 xelatex 编译为 PDF
- run.log 包含完整运行日志

---

## 8. 开发者说明

### 关键模块

#### 核心流程
- [src/pipeline.py](src/pipeline.py) - 统一流程编排 + 事件回调
- [src/logger.py](src/logger.py) - 统一日志 + GUI 回调日志 handler
- [src/config_schema.py](src/config_schema.py) - 配置校验
- [gui/streamlit_app.py](gui/streamlit_app.py) - Web GUI 主入口

#### 新增功能模块（v2.1+）
- [src/api_config_manager.py](src/api_config_manager.py) - API配置管理，支持6大预设供应商 + 自定义API
- [src/i18n.py](src/i18n.py) - 国际化支持（中文/英文），管理280+条UI文本
- [src/task_queue.py](src/task_queue.py) - 后台任务队列，支持暂停/恢复/取消
- [src/gui_utils.py](src/gui_utils.py) - Streamlit GUI工具函数，集成以上三个模块

详见 [docs/INTEGRATION_GUIDE.md](docs/INTEGRATION_GUIDE.md)。

### 运行测试

```bash
python tests/test_gemini_api.py
```

更多测试可查看 [tests](tests)。

---

## 9. 常见问题

请优先参考 [docs/TROUBLESHOOTING.md](docs/TROUBLESHOOTING.md)。

如果你是首次使用，建议先阅读 [docs/USER_GUIDE.md](docs/USER_GUIDE.md)。
