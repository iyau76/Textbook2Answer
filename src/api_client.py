# -*- coding: utf-8 -*-
"""
统一的 LLM/VLM API 调用封装。
读取 api_config.json，支持多模态（文本 + base64 图片或图片路径）。
当前优先支持 Gemini。
"""
import json
import base64
import os
import time
from pathlib import Path

import requests


def _load_config(config_path: str | None = None) -> dict:
    if config_path is None:
        config_path = Path(__file__).resolve().parent.parent / "api_config.json"
    with open(config_path, "r", encoding="utf-8") as f:
        return json.load(f)


def _image_to_base64(image_path: str, mime_type: str | None = None) -> tuple[str, str]:
    """将本地图片转为 (base64_string, mime_type)。"""
    path = Path(image_path)
    if not path.exists():
        raise FileNotFoundError(f"图片不存在: {image_path}")
    data = path.read_bytes()
    b64 = base64.standard_b64encode(data).decode("ascii")
    if mime_type is None:
        suffix = path.suffix.lower()
        mime_type = {
            ".png": "image/png",
            ".jpg": "image/jpeg",
            ".jpeg": "image/jpeg",
            ".webp": "image/webp",
            ".gif": "image/gif",
        }.get(suffix, "image/png")
    return b64, mime_type


class APIClient:
    """通用 API 客户端，优先使用 Gemini，支持多模态。"""

    def __init__(self, provider: str = "gemini", config_path: str | None = None):
        config = _load_config(config_path)
        if provider not in config:
            raise ValueError(f"未找到配置: {provider}。可用: {list(config.keys())}")
        self._provider = provider
        self._cfg = config[provider]
        self._base_url = self._cfg["base_url"].rstrip("/")
        self._api_key = self._cfg["api_key"]
        self._model = self._cfg.get("model", "")
        self._timeout = int(self._cfg.get("timeout_seconds", 120))
        self._max_retries = int(self._cfg.get("max_retries", 2))
        self._retry_backoff = float(self._cfg.get("retry_backoff_seconds", 2.0))
        self._temperature = float(self._cfg.get("temperature", 0.2))
        self._max_tokens = self._cfg.get("max_tokens", None)

    def chat(
        self,
        messages: list[dict],
        *,
        image_path: str | None = None,
        image_base64: str | None = None,
        image_mime: str | None = None,
        model: str | None = None,
    ) -> str:
        """
        发送对话请求。支持纯文本或文本+图片。
        messages: [{"role": "user"/"system", "content": "..."}, ...]
        image_path: 可选，本地图片路径（与 image_base64 二选一）
        image_base64: 可选，图片 base64（与 image_path 二选一）
        image_mime: 与 image_base64 配合使用，如 image/png
        返回: 助手回复的文本。
        """
        last_err: Exception | None = None
        for attempt in range(self._max_retries + 1):
            try:
                if self._provider == "gemini":
                    return self._chat_gemini(
                        messages,
                        image_path=image_path,
                        image_base64=image_base64,
                        image_mime=image_mime,
                        model=model,
                    )
                # OpenAI 兼容接口（DeepSeek / GPT / 自定义节点）
                return self._chat_openai_compatible(
                    messages,
                    image_path=image_path,
                    image_base64=image_base64,
                    image_mime=image_mime,
                    model=model,
                )
            except (requests.Timeout, requests.ConnectionError) as e:
                last_err = e
            except requests.HTTPError as e:
                last_err = e
                status = getattr(e.response, "status_code", None)
                # 仅对常见临时错误重试
                if status not in (429, 500, 502, 503, 504):
                    raise

            if attempt < self._max_retries:
                time.sleep(self._retry_backoff * (2**attempt))

        assert last_err is not None
        raise last_err

    def _chat_gemini(
        self,
        messages: list[dict],
        *,
        image_path: str | None = None,
        image_base64: str | None = None,
        image_mime: str | None = None,
        model: str | None = None,
    ) -> str:
        """Gemini REST API：generateContent，支持 inline_data 图片。"""
        parts = []

        # 若提供图片，先插入图片 part
        if image_path:
            b64, mime = _image_to_base64(image_path)
            parts.append({"inline_data": {"mime_type": mime, "data": b64}})
        elif image_base64:
            mime = image_mime or "image/png"
            parts.append({"inline_data": {"mime_type": mime, "data": image_base64}})

        # 合并所有文本为一条 user content
        text_parts = []
        for m in messages:
            role = m.get("role", "user")
            content = m.get("content", "")
            if role == "system":
                text_parts.append(f"[System]\n{content}")
            else:
                text_parts.append(content)
        text = "\n\n".join(text_parts)
        parts.append({"text": text})

        body = {"contents": [{"role": "user", "parts": parts}]}
        use_model = model or self._model
        url = f"{self._base_url}/models/{use_model}:generateContent"
        params = {"key": self._api_key}

        # Gemini generationConfig（可选）
        gen_cfg = {}
        if self._max_tokens is not None:
            gen_cfg["maxOutputTokens"] = int(self._max_tokens)
        if self._temperature is not None:
            gen_cfg["temperature"] = float(self._temperature)
        if gen_cfg:
            body["generationConfig"] = gen_cfg

        resp = requests.post(url, params=params, json=body, timeout=self._timeout)
        resp.raise_for_status()
        data = resp.json()

        # 解析候选中的文本
        candidates = data.get("candidates", [])
        if not candidates:
            return ""
        parts_out = candidates[0].get("content", {}).get("parts", [])
        for p in parts_out:
            if "text" in p:
                return p["text"].strip()
        return ""

    def _chat_openai_compatible(
        self,
        messages: list[dict],
        *,
        image_path: str | None = None,
        image_base64: str | None = None,
        image_mime: str | None = None,
        model: str | None = None,
    ) -> str:
        """
        OpenAI 兼容的 Chat Completions 接口。
        约定：base_url 指向根（如 https://xxx/v1 或 https://ark.../api/v3），最终请求 {base_url}/chat/completions。
        """
        use_model = model or self._model
        if not use_model:
            raise ValueError(f"provider={self._provider} 未配置 model，且未传入 model 参数")

        # 兼容两种 base_url 写法：
        # 1) base_url 是根（.../v1 或 .../api/v3） -> 自动拼 /chat/completions
        # 2) base_url 已经是完整的 chat/completions endpoint -> 直接使用
        if self._base_url.endswith("/chat/completions"):
            url = self._base_url
        else:
            url = f"{self._base_url}/chat/completions"
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }

        # 若传入图片，采用 OpenAI 视觉兼容的 content=[{type:text...},{type:image_url...}] 结构
        if image_path and not image_base64:
            b64, mime = _image_to_base64(image_path)
            image_base64, image_mime = b64, mime

        oai_messages: list[dict] = []
        for m in messages:
            role = m.get("role", "user")
            content = m.get("content", "")
            if image_base64 and role == "user":
                mime = image_mime or "image/png"
                oai_messages.append(
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": str(content)},
                            {
                                "type": "image_url",
                                "image_url": {"url": f"data:{mime};base64,{image_base64}"},
                            },
                        ],
                    }
                )
                image_base64 = None  # 只附带一次
            else:
                oai_messages.append({"role": role, "content": str(content)})

        body = {
            "model": use_model,
            "messages": oai_messages,
            "temperature": self._temperature,
        }
        if self._max_tokens is not None:
            body["max_tokens"] = int(self._max_tokens)

        resp = requests.post(url, headers=headers, json=body, timeout=self._timeout)
        resp.raise_for_status()
        data = resp.json()
        choices = data.get("choices") or []
        if not choices:
            return ""
        msg = choices[0].get("message") or {}
        return (msg.get("content") or "").strip()


# 便捷函数：仅文本
def chat_text(system: str, user: str, provider: str = "gemini", config_path: str | None = None) -> str:
    """仅文本对话。"""
    client = APIClient(provider=provider, config_path=config_path)
    return client.chat([
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ])


# 便捷函数：带一张图片
def chat_with_image(
    system: str,
    user: str,
    image_path: str,
    provider: str = "gemini",
    config_path: str | None = None,
) -> str:
    """带一张本地图片的对话。"""
    client = APIClient(provider=provider, config_path=config_path)
    return client.chat(
        [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        image_path=image_path,
    )
