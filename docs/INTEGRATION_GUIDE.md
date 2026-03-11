# Textbook2Answer Pro - 新功能集成指南

## 🎉 新增功能概览

本次更新包含了多个重要功能扩展：

1. **API配置管理可视化** - 用户可视化配置多家API提供商
2. **多语言支持** - 中文和英文UI，可随时切换
3. **后台任务队列** - 支持暂停、恢复、取消任务
4. **LaTeX格式修复** - 自动处理模型输出中的转义问题

## 📦 新建模块说明

### 1. `src/api_config_manager.py`
管理API配置，支持多个预设提供商和自定义配置。

**主要特性**:
- 预设提供商：Gemini, DeepSeek, Qwen, Claude, Zhipu, OpenAI
- VLM（视觉）和LLM（文本）分开配置
- 支持自定义OpenAI兼容API
- 自动保存/加载配置

**使用示例**:
```python
from src.api_config_manager import APIConfigManager

manager = APIConfigManager("config/api_config.json")

# 添加预设提供商
manager.add_preset_provider("gemini", "your-api-key", "gemini-2.0-flash")

# 添加自定义提供商
manager.add_custom_provider(
    provider_key="local-api",
    base_url="http://localhost:8000",
    api_key="your-key",
    model="your-model",
)

manager.save()
```

### 2. `src/i18n.py`
国际化支持，管理多语言UI文本。

**支持的语言**:
- `"zh"` - 中文
- `"en"` - 英文

**使用示例**:
```python
from src.i18n import get_i18n, set_i18n_language

i18n = get_i18n("zh")
print(i18n("title"))  # 输出中文标题

set_i18n_language("en")  # 切换至英文
```

### 3. `src/task_queue.py`
后台任务队列管理系统。

**任务状态**:
- `PENDING` - 等待执行
- `RUNNING` - 运行中
- `PAUSED` - 已暂停
- `COMPLETED` - 已完成
- `FAILED` - 失败
- `CANCELLED` - 已取消

**使用示例**:
```python
from src.task_queue import TaskQueue, TaskStatus

queue = TaskQueue()

# 添加任务
task = queue.add_task(
    task_id="task_001",
    project_id="project_1",
    action="full",
    solve_provider="gemini",
)

# 暂停任务
queue.pause_task("task_001")

# 恢复任务
queue.resume_task("task_001")

# 取消任务
queue.cancel_task("task_001")

# 获取任务进度
task = queue.get_task("task_001")
print(f"进度: {task.progress.percentage}%")
```

### 4. `src/gui_utils.py`
GUI工具函数，集成所有新功能到Streamlit界面。

**提供的函数**:
- `init_gui_state()` - 初始化GUI状态
- `render_language_settings()` - 渲染语言设置
- `render_api_config_section()` - 渲染API配置界面
- `render_task_queue_section()` - 渲染任务队列界面

## 🔧 集成到GUI的步骤

在 `gui/streamlit_app.py` 中添加以下代码：

### 步骤1: 导入新模块
```python
from src.gui_utils import (
    init_gui_state,
    render_language_settings,
    render_api_config_section,
    render_task_queue_section,
)
```

### 步骤2: 初始化状态
在 `st.set_page_config()` 之后添加：
```python
init_gui_state()
i18n = st.session_state.i18n
```

### 步骤3: 添加设置侧边栏
在右上角添加设置：
```python
st.sidebar.divider()
render_language_settings()
render_api_config_section()
render_task_queue_section()
```

### 步骤4: 更新页面标题（使用i18n）
```python
st.title(i18n("title"))
st.caption(i18n("subtitle"))
```

## 📝 LaTeX修复验证

修复后的问题：
- ✅ `\begin{equation}\n` 中的 `\n` 已移除
- ✅ `\begin{cases} \n` 中的 `\n` 已处理
- ✅ `\label{eq:...}\n` 中的 `\n` 已清理
- ✅ cases环境中的单个 `\` 转换为 `\\`

## 🌍 多语言系统提示词

已为reasoning_solver.py添加英文系统提示词：
- 中文版本 (默认): `REASONING_SYSTEM`
- 英文版本: `REASONING_SYSTEM_EN`
- 获取函数: `get_reasoning_system_prompt(language)`

## ⚠️ 重要提示

1. **API Key安全**:
   - API Key存储在本地 `config/api_config.json`
   - 从不上传至云端
   - 生产环境建议使用环境变量

2. **任务队列持久化**:
   - 任务信息自动保存至 `.t2a_queue/queue.json`
   - 应用重启后可恢复任务状态

3. **语言切换**:
   - 语言设置在Streamlit会话中有效
   - 刷新页面需要重新选择
   - 可将语言偏好保存至配置文件

## 🎯 后续改进建议

1. **用户偏好持久化**：保存用户的语言选择和API配置偏好
2. **任务日志详情**：显示每个任务的详细执行日志
3. **API测试功能**：快速测试API连接是否正常
4. **批量任务创建**：支持一次创建多个任务
5. **Web版本**：将Streamlit upgrade为FastAPI + React的混合模式

## 📞 技术支持

如遇到问题，请检查：
1. `config/api_config.json` 是否存在且格式正确
2. API Key是否有效
3. 网络连接是否正常
4. `.t2a_queue/` 目录权限是否正确

---

**版本**: 2.0.0+  
**最后更新**: 2026-03-10
