import json
import os

class Translator:
    def __init__(self):
        self.translations = {}
        self._load_translations()

    def _load_translations(self):
        translations_dir = os.path.join(os.path.dirname(__file__), '../translations')
        for filename in os.listdir(translations_dir):
            if filename.endswith('.json'):
                language = filename.split('.')[0]
                with open(os.path.join(translations_dir, filename), 'r', encoding='utf-8') as f:
                    self.translations[language] = json.load(f)

    def get_text(self, key, language='te'):
        """Get text for given key in specified language"""
        try:
            # Split the key by dots to traverse nested dictionary
            parts = key.split('.')
            value = self.translations.get(language, {})
            for part in parts:
                value = value.get(part, key)
            return value if isinstance(value, str) else key
        except:
            return key

translator = Translator()
