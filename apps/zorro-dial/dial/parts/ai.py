"""AI: the chat with zorro-ai. The dial draws it as a panel (dial/chatview.py) and keeps the
conversation (dial/chat.py); this is the part's place in the hub."""
from .base import Part


class Ai(Part):
    key, title = 'ai', 'AI'
    tree = False
    chat = True                         # the fan gives way to the chat panel

    def preview(self):
        return 'AI', 'Chat', ['type a question']

    def centre(self):
        return 'new chat', None         # the dial empties its own chat (chatview.chat_new)
