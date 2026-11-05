from app.providers.openai_compatible import OpenAICompatibleChatProvider


class GroqProvider(OpenAICompatibleChatProvider):
    name = "groq"
    endpoint = "https://api.groq.com/openai/v1/chat/completions"
    api_key_variable = "GROQ_API_KEY"
