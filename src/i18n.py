# -*- coding: utf-8 -*-
"""
多语言支持模块。
管理UI文本和系统提示词的多语言版本。
"""
from typing import Dict, Literal, Optional


Language = Literal["zh", "en"]


class I18n:
    """国际化管理器。"""

    TRANSLATIONS: Dict[Language, Dict[str, str]] = {
        "zh": {
            # UI标签
            "title": "📚 Textbook2Answer Pro 工作台",
            "subtitle": "从\"手工配置工具\"升级为\"项目向导 + 任务中心 + 审阅交付\"",
            
            # 标签页
            "tab_wizard": "🧭 新建项目向导",
            "tab_center": "📁 项目中心",
            "tab_task": "🚀 任务中心",
            "tab_review": "🧪 审阅与修订",
            "tab_export": "📦 导出与报告",
            
            # Step 1
            "step_basic": "Step 1 · 基本信息",
            "label_title": "项目/书名",
            "label_pdf": "PDF 路径",
            "pdf_select": "快速选择本地 PDF",
            "pdf_manual": "(手动输入)",
            "pdf_tip": "例如 D:/Books/量子力学.pdf",
            
            # Step 2
            "step_quality": "Step 2 · 质量档位",
            "label_profile": "运行档位",
            "profile_fast": "极速",
            "profile_balanced": "均衡",
            "profile_high": "高质量",
            "profile_custom": "自定义",
            "profile_tip": "极速=快，均衡=默认推荐，高质量=更强调答案质量",
            
            # Step 3
            "step_chapters": "Step 3 · 章节与页码",
            "label_count": "章节数量",
            "label_chapter_name": "章节 {i} 名称",
            "label_chapter_pages": "章节 {i} 页码（支持 15-18,20）",
            "chapter_preview": "章节 {i} 解析页码：{pages}",
            
            # Step 4
            "step_preview": "Step 4 · 章节页码可视化预览",
            "label_select_chapter": "选择要预览的章节",
            "btn_preview": "生成缩略图预览",
            "preview_success": "已生成 {count} 张预览图",
            
            # Step 5
            "step_create": "Step 5 · 创建项目",
            "btn_create": "✅ 保存项目并设为当前项目",
            
            # 错误消息
            "err_title_empty": "书名不能为空",
            "err_pages_error": "请先修复页码格式错误",
            "err_no_chapters": "至少需要一个有效章节",
            "err_pdf_invalid": "PDF 路径无效，请检查文件是否存在",
            "success_create": "项目创建成功：{title}",
            
            # 项目中心
            "projects_list": "项目列表",
            "no_projects": "暂无项目，请先在\"新建项目向导\"创建",
            "btn_select": "设为当前项目",
            "btn_validate": "校验当前项目配置",
            "validate_success": "校验通过",
            
            # API配置
            "section_api": "API 配置可视化编辑",
            "label_api_file": "api_config.json 内容",
            "btn_save_api": "保存 API 配置",
            "success_save": "已保存：{path}",
            
            # 任务中心
            "task_center": "任务中心",
            "action_full": "全流程运行",
            "action_extract": "仅执行提取",
            "action_solve": "仅执行求解",
            "action_latex": "仅组装 LaTeX",
            "action_retry": "失败题一键重跑",
            
            "log_title": "📋 实时日志",
            "btn_execute": "🚀 开始执行",
            "btn_pause": "⏸ 暂停",
            "btn_resume": "▶ 恢复",
            "btn_cancel": "✕ 取消",
            
            # 设置
            "settings": "设置",
            "language": "语言",
            "language_zh": "中文",
            "language_en": "English",
            
            # 界面元素
            "metric_images": "图片",
            "metric_tasks": "题目",
            "metric_answers": "答案",
            "metric_failed": "失败",
            "metric_latex": "LaTeX",
            
            # 审阅
            "review_title": "审阅与修订",
            "tab_review_tasks": "📋 题目修订",
            "tab_review_answers": "📝 答案修订",
            "tab_review_failed": "⚠️ 失败题管理",
            
            # 导出
            "export_title": "导出与报告",
        },
        "en": {
            # UI Labels
            "title": "📚 Textbook2Answer Pro Workspace",
            "subtitle": "Upgrade from \"manual configuration tool\" to \"project wizard + task center + review & delivery\"",
            
            # Tabs
            "tab_wizard": "🧭 New Project Wizard",
            "tab_center": "📁 Project Center",
            "tab_task": "🚀 Task Center",
            "tab_review": "🧪 Review & Revise",
            "tab_export": "📦 Export & Report",
            
            # Step 1
            "step_basic": "Step 1 · Basic Information",
            "label_title": "Project/Book Title",
            "label_pdf": "PDF Path",
            "pdf_select": "Quick Select Local PDF",
            "pdf_manual": "(Manual Input)",
            "pdf_tip": "e.g., D:/Books/Quantum_Mechanics.pdf",
            
            # Step 2
            "step_quality": "Step 2 · Quality Profile",
            "label_profile": "Execution Profile",
            "profile_fast": "Fast",
            "profile_balanced": "Balanced",
            "profile_high": "High Quality",
            "profile_custom": "Custom",
            "profile_tip": "Fast=quick, Balanced=recommended default, High Quality=emphasize answer quality",
            
            # Step 3
            "step_chapters": "Step 3 · Chapters and Pages",
            "label_count": "Chapter Count",
            "label_chapter_name": "Chapter {i} Name",
            "label_chapter_pages": "Chapter {i} Pages (support 15-18,20)",
            "chapter_preview": "Chapter {i} parsed pages: {pages}",
            
            # Step 4
            "step_preview": "Step 4 · Chapter Pages Visualization",
            "label_select_chapter": "Select chapter to preview",
            "btn_preview": "Generate Thumbnail Preview",
            "preview_success": "Generated {count} preview images",
            
            # Step 5
            "step_create": "Step 5 · Create Project",
            "btn_create": "✅ Save Project and Set as Current",
            
            # Error Messages
            "err_title_empty": "Book title cannot be empty",
            "err_pages_error": "Please fix page format errors first",
            "err_no_chapters": "At least one valid chapter is required",
            "err_pdf_invalid": "Invalid PDF path, please check if file exists",
            "success_create": "Project created successfully: {title}",
            
            # Project Center
            "projects_list": "Project List",
            "no_projects": "No projects yet, please create one in the wizard",
            "btn_select": "Set as Current Project",
            "btn_validate": "Validate Project Configuration",
            "validate_success": "Validation passed",
            
            # API Configuration
            "section_api": "API Configuration Editor",
            "label_api_file": "api_config.json Content",
            "btn_save_api": "Save API Configuration",
            "success_save": "Saved: {path}",
            
            # Task Center
            "task_center": "Task Center",
            "action_full": "Full Pipeline",
            "action_extract": "Extract Only",
            "action_solve": "Solve Only",
            "action_latex": "Build LaTeX Only",
            "action_retry": "Retry Failed Questions",
            
            "log_title": "📋 Live Logs",
            "btn_execute": "🚀 Execute",
            "btn_pause": "⏸ Pause",
            "btn_resume": "▶ Resume",
            "btn_cancel": "✕ Cancel",
            
            # Settings
            "settings": "Settings",
            "language": "Language",
            "language_zh": "中文",
            "language_en": "English",
            
            # UI Elements
            "metric_images": "Images",
            "metric_tasks": "Questions",
            "metric_answers": "Answers",
            "metric_failed": "Failed",
            "metric_latex": "LaTeX",
            
            # Review
            "review_title": "Review & Revise",
            "tab_review_tasks": "📋 Task Review",
            "tab_review_answers": "📝 Answer Review",
            "tab_review_failed": "⚠️ Failed Questions",
            
            # Export
            "export_title": "Export & Report",
        }
    }

    def __init__(self, language: Language = "zh"):
        self.language = language

    def set_language(self, language: Language) -> None:
        """设置语言。"""
        if language not in self.TRANSLATIONS:
            raise ValueError(f"Unsupported language: {language}")
        self.language = language

    def get(self, key: str, **kwargs) -> str:
        """获取翻译文本。"""
        text = self.TRANSLATIONS[self.language].get(key, key)
        if kwargs:
            return text.format(**kwargs)
        return text

    def __call__(self, key: str, **kwargs) -> str:
        """快速调用接口。"""
        return self.get(key, **kwargs)


# 全局单例
_i18n_instance: Optional[I18n] = None


def get_i18n(language: Language = "zh") -> I18n:
    """获取国际化实例。"""
    global _i18n_instance
    if _i18n_instance is None:
        _i18n_instance = I18n(language)
    return _i18n_instance


def set_i18n_language(language: Language) -> None:
    """设置全局语言。"""
    get_i18n().set_language(language)
