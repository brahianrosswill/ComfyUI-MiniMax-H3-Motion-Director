from __future__ import annotations

from pathlib import Path
import re


README = Path(__file__).resolve().parents[1] / "README.md"


def test_readme_is_comprehensively_written_in_simplified_chinese():
    text = README.read_text(encoding="utf-8")
    cjk_count = len(re.findall(r"[\u4e00-\u9fff]", text))
    assert cjk_count > 3000
    for heading in (
        "## 安装",
        "## 节点输入",
        "## 节点输出",
        "## 任务模式",
        "## Motion Context",
        "## Color Re-anchor",
        "## Source Bridge（仅 V2V/RV2V）",
        "## 全局 32 像素空间对齐",
        "## 缓存与选择运行",
        "## 已知限制",
        "## 许可证与上游来源",
    ):
        assert heading in text


def test_readme_does_not_present_removed_or_misleading_behavior_as_current():
    text = README.read_text(encoding="utf-8")
    for stale in (
        "Bernini-style",
        "Source Overlap",
        "Best Cut",
        "RGB MAD",
        "yellow correction",
        "yellow drift",
        "Motion Context 22",
        "22 frames baseline",
        "### R2V 参考集合继承",
        "后续空组继承最近一个完整的显式参考集合",
        "16 像素仍可用",
        "动态 32 像素空间对齐",
    ):
        assert stale not in text

    assert "降低多段链式生成中的累积性色彩漂移" in text
    assert "它不是针对某一种颜色方向的特殊修正" in text
    assert "Source Bridge v1 不运行 Motion Context 的 generated-audio continuation" in text
    assert "所有 MiniMax H3 任务统一使用 32 像素空间网格" in text
    assert "V2V/RV2V `<Video 1>`" in text
    assert "Common Asset Pool" in text
    assert "Common → Local" in text
    assert "A、B、C、D" in text
    assert "latent-first" in text
    assert "Reroute" in text
    assert "仅尾帧" in text
    assert "Prompt chip" in text
