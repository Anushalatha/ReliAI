from app.providers.openai_compatible import OpenAICompatibleChatProvider


class TogetherProvider(OpenAICompatibleChatProvider):
    name = "together"
    endpoint = "https://api.together.ai/v1/chat/completions"
    api_key_variable = "TOGETHER_API_KEY"
