# -*- coding: utf-8 -*-
"""
Phase 1: 测试 Gemini API 连通性。
1) 基本文本对话
2) 发送一张本地测试图片进行识别
"""
import os
import sys

# 将项目根目录加入 path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.api_client import APIClient, chat_text, chat_with_image


def test_text():
    """测试纯文本对话。"""
    print("=== 测试 1: 纯文本对话 ===")
    try:
        out = chat_text(
            system="你是一个简洁的助手，用一句话回答。",
            user="请用中文说：你好，我是 Gemini。",
        )
        print("回复:", out)
        assert out, "回复不应为空"
        print("通过.\n")
    except Exception as e:
        print("失败:", e)
        raise


def test_vision():
    """测试带图片的对话。若无本地测试图则跳过。"""
    print("=== 测试 2: 带图片的对话 ===")
    # 优先使用 output/images 下已有页面图；否则用项目根目录下的 test_image.png
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    candidates = [
        os.path.join(root, "output", "images", "page_1.png"),
        os.path.join(root, "test_image.png"),
        os.path.join(root, "input", "test.png"),
    ]
    image_path = None
    for p in candidates:
        if os.path.isfile(p):
            image_path = p
            break
    if not image_path:
        print("未找到测试图片，跳过视觉测试。请放置 test_image.png 于项目根目录或先运行 PDF 切片生成 output/images/page_*.png")
        return
    try:
        out = chat_with_image(
            system="你是一个图像识别助手。请用一句话描述这张图片的内容或文字。",
            user="请描述这张图片。",
            image_path=image_path,
        )
        print("回复:", out)
        assert out, "回复不应为空"
        print("通过.\n")
    except Exception as e:
        print("失败:", e)
        raise


if __name__ == "__main__":
    test_text()
    test_vision()
    print("All tests passed.")
