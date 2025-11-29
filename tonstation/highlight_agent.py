import threading

import sidusai as sai
import sidusai.core.plugin as _cp
import sidusai.plugins.deepseek as ds


class WeeklyHighlightTask(sai.CompletedAgentTask):
    """Task wrapper for digest generation."""


class WeeklyHighlightAgent(sai.Agent):
    """
    SidusAI agent that uses DeepSeek to generate the weekly digest.
    """

    def __init__(self, api_key: str, system_prompt: str, model_name: str = None):
        super().__init__('tonstation_highlight_agent')
        self.system_prompt = system_prompt

        plugin = ds.DeepSeekPlugin(api_key=api_key, model_name=model_name)
        plugin.apply_plugin(self)

        task_skill_names = _cp.build_and_register_task_skill_names(
            [ds.skills.ds_chat_transform_skill], self
        )
        self.task_registration(WeeklyHighlightTask, skill_names=task_skill_names)

    def build_digest_sync(self, user_prompt: str, timeout: int = 120) -> str:
        """
        Build digest synchronously by waiting for the task completion.
        """
        if not self.is_builded:
            self.application_build()

        latch = threading.Event()
        result = {'text': None}

        def _handler(chat: sai.ChatAgentValue):
            result['text'] = chat.last_content()
            latch.set()

        chat = sai.ChatAgentValue([])
        chat.append_system(self.system_prompt)
        chat.append_user(user_prompt)

        task = WeeklyHighlightTask(self).data(chat).then(_handler)
        self.task_execute(task)
        latch.wait(timeout=timeout)
        if not latch.is_set():
            raise TimeoutError('Digest generation timed out')
        return result['text'] or ''


DEFAULT_SYSTEM_PROMPT = (
    "You are Ton Station's Weekly Highlight Builder. "
    "Given raw Telegram messages, produce a crisp Markdown digest with sections: "
    "1) Quick stats (counts, activity window, top authors). "
    "2) Top threads (2-5 bullets with titles + why they matter). "
    "3) Emerging topics (2-3 bullets). "
    "4) Recommended pins/actions (next steps for moderators). "
    "Keep it concise, avoid speculation, keep URLs/authors if present, and stay within 400-600 words."
)
