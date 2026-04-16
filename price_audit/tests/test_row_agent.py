"""行审核 agent 提示词测试。"""

from django.test import SimpleTestCase

from price_audit.agent.row_agent import ROW_AGENT_SYSTEM_PROMPT


class RowAgentPromptTests(SimpleTestCase):
    """锁定核心审核顺序，避免提示词被弱化。"""

    def test_system_prompt_requires_business_mode_before_pricing(self):
        self.assertIn("先判断费用属性，再判断计量口径，再判断价格", ROW_AGENT_SYSTEM_PROMPT)
        self.assertIn("价格判断只能基于本地标准价候选", ROW_AGENT_SYSTEM_PROMPT)
        self.assertIn("包边、收边、踢脚线、压边条默认按 m", ROW_AGENT_SYSTEM_PROMPT)
        self.assertIn("如果价格证据不足，不要强行审减", ROW_AGENT_SYSTEM_PROMPT)
