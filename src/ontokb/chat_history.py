"""Validate client conversation memory without accepting privileged roles."""

MAX_MESSAGES = 20
MAX_CHARACTERS = 32_000


def validate_history(history):
    if not isinstance(history, list) or len(history) > MAX_MESSAGES:
        raise ValueError('history must be a list of at most 20 messages')
    if len(history) % 2:
        raise ValueError('history must contain completed user/assistant pairs')
    result = []
    for index, message in enumerate(history):
        role = 'user' if index % 2 == 0 else 'assistant'
        if not isinstance(message, dict) or message.get('role') != role:
            raise ValueError('history roles must alternate user and assistant')
        content = message.get('content')
        if not isinstance(content, str) or not content.strip():
            raise ValueError('history content must be nonempty text')
        result.append({'role': role, 'content': content})
    if sum(len(message['content']) for message in result) > MAX_CHARACTERS:
        raise ValueError('history must be at most 32000 characters')
    return result
