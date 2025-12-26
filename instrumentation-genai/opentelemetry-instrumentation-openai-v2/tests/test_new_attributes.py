# Copyright The OpenTelemetry Authors
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Tests for new trace attributes and metrics."""

import json

from opentelemetry.instrumentation.openai_v2.utils import (
    messages_to_json,
    tools_to_json,
)


def test_messages_to_json_with_content():
    """Test messages_to_json with content capture enabled"""
    messages = [
        {"role": "user", "content": "Hello"},
        {"role": "assistant", "content": "Hi there"},
    ]
    
    result = messages_to_json(messages, capture_content=True)
    parsed = json.loads(result)
    
    assert len(parsed) == 2
    assert parsed[0]["role"] == "user"
    assert parsed[0]["content"] == "Hello"
    assert parsed[1]["role"] == "assistant"
    assert parsed[1]["content"] == "Hi there"


def test_messages_to_json_without_content():
    """Test messages_to_json with content capture disabled"""
    messages = [
        {"role": "user", "content": "Hello"},
        {"role": "assistant", "content": "Hi there"},
    ]
    
    result = messages_to_json(messages, capture_content=False)
    parsed = json.loads(result)
    
    assert len(parsed) == 2
    assert parsed[0]["role"] == "user"
    assert "content" not in parsed[0]
    assert parsed[1]["role"] == "assistant"
    assert "content" not in parsed[1]


def test_messages_to_json_with_tool_calls():
    """Test messages_to_json with tool calls"""
    messages = [
        {
            "role": "assistant",
            "tool_calls": [
                {
                    "id": "call_123",
                    "type": "function",
                    "function": {
                        "name": "get_weather",
                        "arguments": '{"location": "Boston"}',
                    },
                }
            ],
        }
    ]
    
    result = messages_to_json(messages, capture_content=True)
    parsed = json.loads(result)
    
    assert len(parsed) == 1
    assert parsed[0]["role"] == "assistant"
    assert "tool_calls" in parsed[0]
    assert len(parsed[0]["tool_calls"]) == 1
    assert parsed[0]["tool_calls"][0]["id"] == "call_123"
    assert parsed[0]["tool_calls"][0]["type"] == "function"
    assert parsed[0]["tool_calls"][0]["function"]["name"] == "get_weather"


def test_messages_to_json_with_tool_message():
    """Test messages_to_json with tool message"""
    messages = [
        {
            "role": "tool",
            "tool_call_id": "call_123",
            "content": "The weather is sunny",
        }
    ]
    
    result = messages_to_json(messages, capture_content=True)
    parsed = json.loads(result)
    
    assert len(parsed) == 1
    assert parsed[0]["role"] == "tool"
    assert parsed[0]["tool_call_id"] == "call_123"
    assert parsed[0]["content"] == "The weather is sunny"


def test_tools_to_json():
    """Test tools_to_json"""
    tools = [
        {
            "type": "function",
            "function": {
                "name": "get_current_weather",
                "description": "Get the current weather",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "location": {"type": "string"},
                    },
                },
            },
        }
    ]
    
    result = tools_to_json(tools)
    parsed = json.loads(result)
    
    assert len(parsed) == 1
    assert parsed[0]["type"] == "function"
    assert parsed[0]["function"]["name"] == "get_current_weather"
    assert parsed[0]["function"]["description"] == "Get the current weather"
    # Parameters should not be included to avoid large attributes
    assert "parameters" not in parsed[0]["function"]


def test_tools_to_json_empty():
    """Test tools_to_json with empty list"""
    result = tools_to_json([])
    assert result is None


def test_tools_to_json_none():
    """Test tools_to_json with None"""
    result = tools_to_json(None)
    assert result is None
