# Textbook2Answer 用户操作指南（GUI + CLI）

本指南对应 Pro 工作台（Phase1+2），覆盖：

1. GUI 从 0 到 1 完整操作
2. CLI 常用命令
3. 断点续跑、失败题重跑、审阅修订
4. 导出与版本管理

---

## 1. 运行前准备

### 1.1 安装依赖

```bash
pip install -r requirements.txt
```

### 1.2 配置 API

复制示例配置并填写密钥：

```bash
cp config/api_config.example.json config/api_config.json
```

程序查找顺序：

1. config/api_config.json
2. 根目录 api_config.json（兼容旧版本）

### 1.3 启动 GUI

```bash
streamlit run gui/streamlit_app.py
```

---

## 2. GUI 操作（推荐）

GUI 采用项目工作台设计，包含 5 个标签页：

1. 新建项目向导
2. 项目中心
3. 任务中心
4. 审阅与修订
5. 导出与报告

### 2.1 新建项目向导

路径：[gui/streamlit_app.py](../gui/streamlit_app.py) 的 `🧭 新建项目向导`

按步骤填写：

1. 项目/书名
2. PDF 路径（可快速选择）
3. 质量档位
4. 章节与页码
5. 保存项目

#### 质量档位说明

- 极速：提取和求解都优先速度
- 均衡：提取快 + 求解稳（默认推荐）
- 高质量：更偏质量
- 自定义：手工指定 extract/solve provider 与模型

#### 页码写法

支持：

- 单页：`15`
- 多页：`15,16,20`
- 范围：`15-20`
- 混合：`15-20,22,25-26`

#### 页码预览

向导支持章节页码可视化预览，会生成缩略图帮助检查页码是否选对。

---

### 2.2 项目中心

路径：`📁 项目中心`

功能：

- 切换当前项目
- 查看项目统计（图片数、题目数、答案数、失败数）
- 预览配置 JSON
- 一键校验配置
- API 配置可视化编辑（无需手改文件）

---

### 2.3 任务中心

路径：`🚀 任务中心`

支持动作：

- 全流程运行
- 仅执行提取
- 仅执行求解
- 仅组装 LaTeX
- 失败题一键重跑

点击开始执行后会显示：

- 阶段状态卡
- 实时日志
- 最近任务记录

---

### 2.4 审阅与修订

路径：`🧪 审阅与修订`

#### 题目修订

可在线修改：

- chapter_name
- content
- has_image
- page_num

还可删除该题已有答案，用于强制重跑。

#### 答案修订

可在线修改：

- solution_process
- knowledge_points
- alternative_methods
- extensions

#### 失败题管理

- 查看失败题列表
- 一键重跑失败题
- 清空失败记录文件

---

### 2.5 导出与报告

路径：`📦 导出与报告`

功能：

- 重新组装 LaTeX
- 下载 final_solution.tex
- 创建版本快照（保存当前 JSON/TEX/日志）
- 生成运行报告（Markdown）

---

## 3. CLI 使用指南

### 3.1 基础

```bash
python main.py [options]
```

### 3.2 常用参数

- --skip-pdf
- --skip-extract
- --skip-solve
- --only-latex
- --config PATH
- --pdf PATH
- --provider NAME
- --extract-provider NAME
- --solve-provider NAME
- --extract-model MODEL
- --solve-model MODEL

### 3.3 典型命令

全流程：

```bash
python main.py
```

只重跑解答：

```bash
python main.py --skip-pdf --skip-extract
```

仅组装 LaTeX：

```bash
python main.py --only-latex
```

Gemini 提取 + DeepSeek 解答：

```bash
python main.py --extract-provider gemini --solve-provider deepseek
```

---

## 4. 断点续跑与失败恢复

### 4.1 断点续跑

- 提取缓存：[output](../output) 下的 `extracted_tasks.json`
- 解答缓存：[output](../output) 下的 `solved_answers.json`

再次运行会自动跳过已完成部分。

### 4.2 失败题恢复

失败题记录在 `solve_failures.json`。

推荐直接使用 GUI 的失败题一键重跑；也可用 CLI 重跑求解阶段。

---

## 5. 输出目录说明

```text
output/
  <book_title>/
    images/
    extracted_tasks.json
    solved_answers.json
    solve_failures.json
    final_solution.tex
    run.log
    versions/   # 版本快照
```

---

## 6. 常见问题

### Q1: 启动 GUI 报 `ModuleNotFoundError: streamlit`

```bash
pip install streamlit
```

### Q2: 配置校验失败

先执行：

```bash
python -m src.config_schema
```

根据提示修复字段。

### Q3: 运行中断了怎么办

直接再次执行任务即可，系统会按缓存续跑。

### Q4: LaTeX 编译报错

优先查看：

- [docs/TROUBLESHOOTING.md](TROUBLESHOOTING.md)
- 输出目录里的 `run.log`
- 输出目录里的 `final_solution.tex`

---

## 7. 建议工作流

首次：

1. 向导创建项目
2. 全流程运行
3. 审阅与修订
4. 导出 LaTeX

增量迭代：

1. 修订少量题目/答案
2. 失败题重跑
3. 仅组装 LaTeX
4. 创建版本快照
