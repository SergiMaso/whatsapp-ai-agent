"""
Basic tests for the restaurant reservation bot
"""

import unittest
from src.config.settings import OPENAI_API_KEY, DATABASE_URL

class TestBasicConfiguration(unittest.TestCase):
    
    def test_environment_variables_exist(self):
        """Test that required environment variables are set"""
        self.assertIsNotNone(OPENAI_API_KEY, "OPENAI_API_KEY must be set")
        self.assertIsNotNone(DATABASE_URL, "DATABASE_URL must be set")
    
    def test_openai_key_format(self):
        """Test that OpenAI key has correct format"""
        if OPENAI_API_KEY:
            self.assertTrue(OPENAI_API_KEY.startswith('sk-'), "OpenAI key should start with 'sk-'")

if __name__ == '__main__':
    unittest.main()