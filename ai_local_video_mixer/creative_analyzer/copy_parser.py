from __future__ import annotations


class CopyStructureParser:
    """Basic advertising copy structure parser.

    This version provides a stable interface. Later versions can use LLMs or
    local language models for deeper semantic classification.
    """

    HOOK_WORDS = ("为什么", "很多人不知道", "不要", "注意", "千万")
    CTA_WORDS = ("立即", "点击", "下载", "领取", "购买")

    def parse(self, text: str) -> dict[str, str]:
        content = text.strip()

        structure = {
            "hook": "",
            "pain": "",
            "solution": "",
            "benefit": "",
            "cta": "",
        }

        if any(word in content for word in self.HOOK_WORDS):
            structure["hook"] = content

        if any(word in content for word in self.CTA_WORDS):
            structure["cta"] = content

        if not structure["hook"] and content:
            structure["solution"] = content

        return structure
