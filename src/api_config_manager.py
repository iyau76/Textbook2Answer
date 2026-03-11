# -*- coding: utf-8 -*-
"""
API 配置管理模块。
支持多个API提供商，包括预设和自定义OpenAI格式。
"""
import json
from pathlib import Path
from typing import Optional, Dict, Any, List, Tuple

import requests


class APIConfigManager:
    """API配置管理器，支持多提供商和自定义配置。"""

    # 预设的API提供商配置模板（模型截至 2026-03）
    PRESET_PROVIDERS = {
        "gemini": {
            "name": "Google Gemini",
            "base_url": "https://generativelanguage.googleapis.com/v1beta",
            "models": [
                "gemini-2.5-flash",
                "gemini-2.5-pro",
                "gemini-2.5-flash-lite",
                "gemini-3-flash-preview",
                "gemini-3.1-pro-preview",
            ],
            "supports_multimodal": True,
            "supports_vision": True,
        },
        "deepseek": {
            "name": "DeepSeek",
            "base_url": "https://api.deepseek.com",
            "models": ["deepseek-chat", "deepseek-reasoner"],
            "supports_multimodal": False,
            "supports_vision": False,
        },
        "qwen": {
            "name": "通义千问 Qwen",
            "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
            "models": ["qwen-max", "qwen-plus", "qwen-turbo", "qwen-vl-max", "qwen-vl-plus"],
            "supports_multimodal": True,
            "supports_vision": True,
        },
        "claude": {
            "name": "Anthropic Claude",
            "base_url": "https://api.anthropic.com/v1",
            "models": ["claude-sonnet-4-20250514", "claude-3.5-sonnet-20241022", "claude-3.5-haiku-20241022"],
            "supports_multimodal": True,
            "supports_vision": True,
        },
        "zhipu": {
            "name": "智谱 GLM",
            "base_url": "https://open.bigmodel.cn/api/paas/v4",
            "models": ["glm-4v-flash", "glm-4-flash", "glm-4-plus", "glm-4-air"],
            "supports_multimodal": True,
            "supports_vision": True,
        },
        "openai": {
            "name": "OpenAI",
            "base_url": "https://api.openai.com/v1",
            "models": ["gpt-4o", "gpt-4o-mini", "o3-mini", "o1-mini"],
            "supports_multimodal": True,
            "supports_vision": True,
        },
    }

    def __init__(self, config_path: Optional[Path | str] = None):
        self.config_path = Path(config_path) if config_path else None
        self.config_data: Dict[str, Dict[str, Any]] = {}
        if self.config_path and self.config_path.exists():
            self.load()

    def load(self) -> None:
        """从文件加载配置。"""
        if not self.config_path or not self.config_path.exists():
            return
        try:
            with open(self.config_path, "r", encoding="utf-8") as f:
                self.config_data = json.load(f)
        except Exception:
            self.config_data = {}

    def save(self) -> None:
        """保存配置到文件。"""
        if not self.config_path:
            raise ValueError("未设置配置文件路径")
        self.config_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.config_path, "w", encoding="utf-8") as f:
            json.dump(self.config_data, f, ensure_ascii=False, indent=2)

    def add_preset_provider(self, provider_key: str, api_key: str, model: Optional[str] = None) -> None:
        """添加预设提供商配置。"""
        if provider_key not in self.PRESET_PROVIDERS:
            raise ValueError(f"未知的提供商: {provider_key}")
        
        preset = self.PRESET_PROVIDERS[provider_key]
        config = {
            "base_url": preset["base_url"],
            "api_key": api_key,
            "model": model or preset["models"][0],
            "timeout_seconds": 120,
            "max_retries": 2,
            "retry_backoff_seconds": 2.0,
            "temperature": 0.2,
            "max_tokens": None,
            "supports_multimodal": preset["supports_multimodal"],
            "supports_vision": preset["supports_vision"],
        }
        self.config_data[provider_key] = config

    def add_custom_provider(
        self,
        provider_key: str,
        base_url: str,
        api_key: str,
        model: str,
        supports_multimodal: bool = True,
        supports_vision: bool = True,
        timeout_seconds: int = 120,
        max_retries: int = 2,
        retry_backoff_seconds: float = 2.0,
        temperature: float = 0.2,
        max_tokens: Optional[int] = None,
    ) -> None:
        """添加自定义提供商配置（OpenAI格式）。"""
        config = {
            "base_url": base_url.rstrip("/"),
            "api_key": api_key,
            "model": model,
            "timeout_seconds": timeout_seconds,
            "max_retries": max_retries,
            "retry_backoff_seconds": retry_backoff_seconds,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "supports_multimodal": supports_multimodal,
            "supports_vision": supports_vision,
        }
        self.config_data[provider_key] = config

    def get_provider_config(self, provider_key: str) -> Optional[Dict[str, Any]]:
        """获取提供商配置。"""
        return self.config_data.get(provider_key)

    def delete_provider(self, provider_key: str) -> None:
        """删除提供商配置。"""
        if provider_key in self.config_data:
            del self.config_data[provider_key]

    def list_providers(self) -> List[Tuple[str, Dict[str, Any]]]:
        """列出所有已配置的提供商。"""
        return list(self.config_data.items())

    def get_available_multimodal_providers(self) -> List[str]:
        """获取支持多模态的提供商列表。"""
        return [
            key for key, config in self.config_data.items()
            if config.get("supports_multimodal", True)
        ]

    def validate_provider(self, provider_key: str) -> Tuple[bool, str]:
        """验证提供商配置是否有效。"""
        config = self.get_provider_config(provider_key)
        if not config:
            return False, f"未找到提供商: {provider_key}"
        
        required_fields = ["base_url", "api_key", "model"]
        for field in required_fields:
            if not config.get(field):
                return False, f"缺少必需字段: {field}"
        
        return True, "配置有效"

    def export_config(self) -> Dict[str, Any]:
        """导出配置（用于保存到文件）。"""
        return self.config_data.copy()

    def import_config(self, config_dict: Dict[str, Any]) -> None:
        """导入配置（从字典）。"""
        self.config_data = config_dict.copy()

    def test_connection(self, provider_key: str) -> Tuple[bool, str]:
        """测试 API 连接是否正常。返回 (成功, 消息)。"""
        config = self.get_provider_config(provider_key)
        if not config:
            return False, f"未找到提供商配置: {provider_key}"

        api_key = config.get("api_key", "")
        base_url = config.get("base_url", "")
        model = config.get("model", "")
        timeout = min(config.get("timeout_seconds", 15), 20)

        if not api_key or not base_url:
            return False, "缺少 api_key 或 base_url"

        try:
            if provider_key == "gemini" or "googleapis.com" in base_url:
                url = f"{base_url.rstrip('/')}/models/{model}?key={api_key}"
                resp = requests.get(url, timeout=timeout)
            else:
                url = f"{base_url.rstrip('/')}/models"
                headers = {"Authorization": f"Bearer {api_key}"}
                resp = requests.get(url, headers=headers, timeout=timeout)

            if resp.status_code == 200:
                return True, "连接成功"
            elif resp.status_code == 401:
                return False, "API Key 无效 (401)"
            else:
                return False, f"HTTP {resp.status_code}: {resp.text[:200]}"
        except requests.Timeout:
            return False, "连接超时"
        except requests.ConnectionError:
            return False, "无法连接到服务器，请检查 Base URL"
        except Exception as e:
            return False, str(e)
