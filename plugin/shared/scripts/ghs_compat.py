#!/usr/bin/env python3
"""Shared runtime compatibility helpers for ghs scripts."""

import sys


def force_utf8_stdio():
    """将 stdout/stderr 强制为 UTF-8,避免在旧式中日韩控制台编码
    (如中文 Windows 的 cp936/GBK)下打印 ✅/中文 等字符时抛 UnicodeEncodeError。

    逐流容错:被替换的非标准流对象可能不支持 reconfigure。
    """
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, OSError, ValueError):
            pass
