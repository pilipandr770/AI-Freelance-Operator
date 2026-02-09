"""
OpenAI API Client for AI Freelance Operator
"""

from openai import OpenAI
from config import Config
import json
import time


class AIClient:
    """OpenAI API client wrapper"""
    
    def __init__(self):
        if not Config.OPENAI_API_KEY:
            raise ValueError("OPENAI_API_KEY is not configured")
        
        self.client = OpenAI(api_key=Config.OPENAI_API_KEY)
        self.model = Config.OPENAI_MODEL
        self.temperature = Config.OPENAI_TEMPERATURE
        self.max_tokens = Config.OPENAI_MAX_TOKENS
    
    def chat_completion(self, messages, temperature=None, max_tokens=None, 
                       response_format=None, tools=None):
        """
        Send a chat completion request to OpenAI
        
        Args:
            messages: List of message dicts with 'role' and 'content'
            temperature: Override default temperature
            max_tokens: Override default max_tokens
            response_format: Optional response format (e.g., {"type": "json_object"})
            tools: Optional function calling tools
        
        Returns:
            dict: Response with content, usage, and metadata
        """
        start_time = time.time()
        
        kwargs = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature or self.temperature,
            "max_tokens": max_tokens or self.max_tokens,
        }
        
        if response_format:
            kwargs["response_format"] = response_format
        
        if tools:
            kwargs["tools"] = tools
        
        try:
            response = self.client.chat.completions.create(**kwargs)
            
            execution_time = int((time.time() - start_time) * 1000)  # ms
            
            # Extract response data
            result = {
                "content": response.choices[0].message.content,
                "role": response.choices[0].message.role,
                "finish_reason": response.choices[0].finish_reason,
                "usage": {
                    "prompt_tokens": response.usage.prompt_tokens,
                    "completion_tokens": response.usage.completion_tokens,
                    "total_tokens": response.usage.total_tokens,
                },
                "execution_time_ms": execution_time,
                "model": response.model,
                "cost": self._calculate_cost(response.usage),
            }
            
            # Handle function calls if present
            if hasattr(response.choices[0].message, 'tool_calls') and response.choices[0].message.tool_calls:
                result["tool_calls"] = response.choices[0].message.tool_calls
            
            return result
            
        except Exception as e:
            raise Exception(f"OpenAI API error: {str(e)}")
    
    def _calculate_cost(self, usage):
        """
        Calculate approximate cost based on token usage
        Prices as of 2024 (adjust as needed)
        """
        # GPT-4 pricing (approximate)
        if "gpt-4" in self.model.lower():
            prompt_price_per_1k = 0.03
            completion_price_per_1k = 0.06
        # GPT-3.5-turbo pricing
        else:
            prompt_price_per_1k = 0.0015
            completion_price_per_1k = 0.002
        
        prompt_cost = (usage.prompt_tokens / 1000) * prompt_price_per_1k
        completion_cost = (usage.completion_tokens / 1000) * completion_price_per_1k
        
        return round(prompt_cost + completion_cost, 6)
    
    def parse_json_response(self, content):
        """
        Parse JSON response from AI
        
        Args:
            content: String content that might be JSON
        
        Returns:
            dict: Parsed JSON or None if invalid
        """
        try:
            # Try to find JSON in code blocks
            if "```json" in content:
                start = content.find("```json") + 7
                end = content.find("```", start)
                content = content[start:end].strip()
            elif "```" in content:
                start = content.find("```") + 3
                end = content.find("```", start)
                content = content[start:end].strip()
            
            return json.loads(content)
        except json.JSONDecodeError:
            return None
    
    def test_connection(self):
        """Test OpenAI API connection"""
        try:
            response = self.chat_completion(
                messages=[{"role": "user", "content": "Say 'OK' if you can read this."}],
                max_tokens=10
            )
            
            if response and response.get("content"):
                print(f"✓ OpenAI API connected (model: {self.model})")
                return True
            return False
            
        except Exception as e:
            print(f"✗ OpenAI API connection failed: {e}")
            return False


# Singleton instance
_ai_client = None

def get_ai_client():
    """Get or create AI client singleton"""
    global _ai_client
    if _ai_client is None:
        _ai_client = AIClient()
    return _ai_client
