# -*- coding: utf-8 -*-
"""
GUI 设置和配置管理模块。
集成多语言切换、API 可视化配置、API 连接测试、任务队列等功能。
所有侧边栏 UI 组件统一由此模块提供。
"""
import streamlit as st
from pathlib import Path

from .api_config_manager import APIConfigManager
from .i18n import get_i18n, set_i18n_language, Language
from .task_queue import TaskQueue, TaskStatus


# ── 初始化 ──────────────────────────────────────────────────────

def init_gui_state():
    """初始化 GUI 全局 session_state，确保所有模块实例可用。"""
    if "language" not in st.session_state:
        st.session_state.language = "zh"

    # 始终重建 i18n 以匹配当前 language（避免切换后不生效）
    lang = st.session_state.language
    if "i18n" not in st.session_state or st.session_state.i18n.language != lang:
        set_i18n_language(lang)
        st.session_state.i18n = get_i18n(lang)

    if "api_config_manager" not in st.session_state:
        root = Path(__file__).resolve().parent.parent
        config_path = root / "config" / "api_config.json"
        st.session_state.api_config_manager = APIConfigManager(config_path)

    if "task_queue" not in st.session_state:
        root = Path(__file__).resolve().parent.parent
        st.session_state.task_queue = TaskQueue(root / ".t2a_queue")

    st.session_state.setdefault("concurrency", 1)


# ── 语言切换 ────────────────────────────────────────────────────

def render_language_settings():
    """侧边栏语言切换。使用 selectbox + on_change 避免 radio 重复渲染问题。"""
    cur = st.session_state.language
    options = ["zh", "en"]
    labels = {"zh": "🇨🇳 中文", "en": "🇺🇸 English"}
    idx = options.index(cur) if cur in options else 0

    def _on_change():
        new_lang = st.session_state["_lang_select"]
        if new_lang != st.session_state.language:
            st.session_state.language = new_lang
            set_i18n_language(new_lang)
            st.session_state.i18n = get_i18n(new_lang)

    st.selectbox(
        "🌐 Language / 语言",
        options=options,
        index=idx,
        format_func=lambda x: labels[x],
        key="_lang_select",
        on_change=_on_change,
    )


# ── API 配置 ────────────────────────────────────────────────────

def render_api_config_section():
    """侧边栏 API 配置面板：统一管理 VLM 和 LLM 提供商。"""
    manager: APIConfigManager = st.session_state.api_config_manager
    is_zh = st.session_state.language == "zh"

    with st.expander("🔑 " + ("API 配置管理" if is_zh else "API Configuration"), expanded=False):

        # ── 已配置列表 ──
        providers = manager.list_providers()
        if providers:
            st.markdown("**" + ("已配置的 API" if is_zh else "Configured APIs") + "**")
            for pkey, pcfg in providers:
                preset = manager.PRESET_PROVIDERS.get(pkey)
                display_name = preset["name"] if preset else pkey
                model_str = pcfg.get("model", "N/A")
                c1, c2, c3 = st.columns([3, 3, 2])
                with c1:
                    st.markdown(f"**{display_name}**")
                with c2:
                    st.caption(model_str)
                with c3:
                    bc1, bc2 = st.columns(2)
                    with bc1:
                        if st.button("🧪", key=f"test_{pkey}",
                                     help="测试连接" if is_zh else "Test connection"):
                            ok, msg = manager.test_connection(pkey)
                            if ok:
                                st.success("✅ " + msg)
                            else:
                                st.error("❌ " + msg)
                    with bc2:
                        if st.button("🗑", key=f"del_{pkey}",
                                     help="删除" if is_zh else "Delete"):
                            manager.delete_provider(pkey)
                            manager.save()
                            st.rerun()
            st.divider()

        # ── 添加 / 更新配置 ──
        st.markdown("**" + ("添加或更新 API" if is_zh else "Add / Update API") + "**")

        all_options = list(manager.PRESET_PROVIDERS.keys()) + ["custom"]
        display_map = {k: v["name"] for k, v in manager.PRESET_PROVIDERS.items()}
        display_map["custom"] = "🛠 自定义 (OpenAI-Compatible)" if is_zh else "🛠 Custom (OpenAI-Compatible)"

        provider_key = st.selectbox(
            "选择提供商" if is_zh else "Select Provider",
            options=all_options,
            format_func=lambda x: display_map.get(x, x),
            key="sidebar_provider_key",
        )

        is_custom = (provider_key == "custom")
        preset = manager.PRESET_PROVIDERS.get(provider_key, {})

        # Base URL
        if is_custom:
            base_url = st.text_input(
                "Base URL",
                value="https://",
                key="sidebar_base_url",
                help="OpenAI 兼容 API 的根地址" if is_zh else "Root URL of OpenAI-compatible API",
            )
        else:
            default_url = preset.get("base_url", "")
            base_url = st.text_input(
                "Base URL",
                value=default_url,
                key="sidebar_base_url",
                help="如需代理可修改此地址" if is_zh else "Modify if using a proxy",
            )

        # API Key
        api_key = st.text_input(
            "API Key",
            type="password",
            key="sidebar_api_key",
        )

        # 模型选择
        if is_custom:
            model = st.text_input(
                "模型名称" if is_zh else "Model Name",
                key="sidebar_model",
                help="输入模型名称，如 gpt-4o" if is_zh else "Enter model name, e.g. gpt-4o",
            )
            custom_name = st.text_input(
                "配置名称（唯一标识）" if is_zh else "Config Name (unique ID)",
                key="sidebar_custom_name",
                help="将以此名称保存到配置文件" if is_zh else "Saved under this name in config",
            )
        else:
            models_list = preset.get("models", [])
            model = st.selectbox(
                "模型" if is_zh else "Model",
                options=models_list,
                key="sidebar_model_select",
            )
            # 也允许手动覆盖
            model_override = st.text_input(
                "或手动输入模型名" if is_zh else "Or enter model name manually",
                key="sidebar_model_override",
                help="留空则使用上方选择" if is_zh else "Leave empty to use selection above",
            )
            if model_override.strip():
                model = model_override.strip()

        # 高级设置
        with st.expander("⚙️ " + ("高级设置" if is_zh else "Advanced Settings"), expanded=False):
            timeout = st.number_input(
                "Timeout (" + ("秒" if is_zh else "sec") + ")",
                value=120, min_value=10,
                key="sidebar_timeout",
            )
            temperature = st.slider(
                "Temperature", 0.0, 2.0, 0.2, 0.1,
                key="sidebar_temperature",
            )
            max_tokens = st.number_input(
                "Max Tokens (0=" + ("不限" if is_zh else "unlimited") + ")",
                value=0, min_value=0,
                key="sidebar_max_tokens",
            )

        # 保存按钮
        if st.button("💾 " + ("保存配置" if is_zh else "Save Configuration"), key="sidebar_save_api"):
            if not api_key.strip():
                st.error("❌ " + ("请输入 API Key" if is_zh else "Please enter API Key"))
            elif not model.strip():
                st.error("❌ " + ("请指定模型" if is_zh else "Please specify a model"))
            else:
                save_key = custom_name.strip() if is_custom else provider_key
                if is_custom and not save_key:
                    st.error("❌ " + ("请输入配置名称" if is_zh else "Please enter config name"))
                else:
                    manager.add_custom_provider(
                        provider_key=save_key,
                        base_url=base_url.strip(),
                        api_key=api_key.strip(),
                        model=model.strip(),
                        timeout_seconds=int(timeout),
                        temperature=temperature,
                        max_tokens=int(max_tokens) if max_tokens > 0 else None,
                    )
                    manager.save()
                    st.success("✅ " + ("已保存" if is_zh else "Saved") + f": {save_key}")
                    st.rerun()


# ── 并发设置 ────────────────────────────────────────────────────

def render_concurrency_settings():
    """侧边栏并发数配置。"""
    is_zh = st.session_state.language == "zh"

    def _on_change():
        st.session_state.concurrency = st.session_state["_concurrency_input"]

    st.number_input(
        "⚡ " + ("并发请求数" if is_zh else "Concurrent Requests"),
        min_value=1,
        max_value=20,
        value=st.session_state.get("concurrency", 1),
        step=1,
        key="_concurrency_input",
        on_change=_on_change,
        help=("同时发送多个 API 请求以加速处理。建议 3-5，过高可能触发限速。"
              if is_zh else
              "Send multiple API requests simultaneously. Recommended 3-5, too high may trigger rate limits."),
    )


# ── 任务队列 ────────────────────────────────────────────────────

def render_task_queue_section():
    """侧边栏任务队列面板。"""
    is_zh = st.session_state.language == "zh"
    queue = st.session_state.task_queue

    with st.expander("📋 " + ("任务队列" if is_zh else "Task Queue")):
        col1, col2 = st.columns(2)
        with col1:
            if st.button("🔄 " + ("刷新" if is_zh else "Refresh"), key="tq_refresh"):
                st.rerun()
        with col2:
            if st.button("🧹 " + ("清理已完成" if is_zh else "Clear Done"), key="tq_clear"):
                removed = queue.clear_completed_tasks(older_than_hours=24)
                st.success(("已清理 " if is_zh else "Cleared ") + str(removed))
                st.rerun()

        tasks = queue.list_tasks()
        if tasks:
            for task in tasks:
                emoji = {
                    TaskStatus.PENDING: "⏳", TaskStatus.RUNNING: "🔄",
                    TaskStatus.PAUSED: "⏸", TaskStatus.COMPLETED: "✅",
                    TaskStatus.FAILED: "❌", TaskStatus.CANCELLED: "🚫",
                }.get(task.status, "")
                st.markdown(f"{emoji} **{task.task_id}** — {task.status.value}")
                if task.progress.total_items > 0:
                    st.progress(task.progress.percentage / 100.0)
                bc1, bc2 = st.columns(2)
                with bc1:
                    if task.status == TaskStatus.RUNNING:
                        if st.button("⏸", key=f"p_{task.task_id}"):
                            queue.pause_task(task.task_id)
                            st.rerun()
                    elif task.status == TaskStatus.PAUSED:
                        if st.button("▶", key=f"r_{task.task_id}"):
                            queue.resume_task(task.task_id)
                            st.rerun()
                with bc2:
                    if task.status not in (TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.CANCELLED):
                        if st.button("✕", key=f"c_{task.task_id}"):
                            queue.cancel_task(task.task_id)
                            st.rerun()
        else:
            st.caption("— " + ("暂无任务" if is_zh else "No tasks"))
