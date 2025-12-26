#!/usr/bin/env python3
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

"""
Example script to demonstrate the new trace attributes and metrics.

This script shows how the new instrumentation captures:
1. gen_ai.input.messages - Input messages as JSON
2. gen_ai.output.messages - Output messages as JSON  
3. gen_ai.input.tools - Tools definitions as JSON
4. Streaming timing metrics (time_to_first_token, time_per_output_token, etc.)
5. Cached tokens metric

Usage:
    export OPENAI_API_KEY=your_api_key_here
    export OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT=true
    python3 example_new_features.py
"""

import json
import os
from openai import OpenAI

from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import ConsoleSpanExporter, SimpleSpanProcessor
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import ConsoleMetricExporter, PeriodicExportingMetricReader
from opentelemetry._logs import set_logger_provider
from opentelemetry.sdk._logs import LoggerProvider
from opentelemetry.sdk._logs.export import ConsoleLogExporter, SimpleLogRecordProcessor

from opentelemetry.instrumentation.openai_v2 import OpenAIInstrumentor

# Set up OpenTelemetry
trace.set_tracer_provider(TracerProvider())
tracer_provider = trace.get_tracer_provider()
tracer_provider.add_span_processor(SimpleSpanProcessor(ConsoleSpanExporter()))

metric_reader = PeriodicExportingMetricReader(ConsoleMetricExporter(), export_interval_millis=1000)
meter_provider = MeterProvider(metric_readers=[metric_reader])

logger_provider = LoggerProvider()
logger_provider.add_log_record_processor(SimpleLogRecordProcessor(ConsoleLogExporter()))
set_logger_provider(logger_provider)

# Instrument OpenAI
OpenAIInstrumentor().instrument(
    tracer_provider=tracer_provider,
    meter_provider=meter_provider,
    logger_provider=logger_provider,
)

# Example 1: Non-streaming chat with input/output messages
print("=" * 80)
print("Example 1: Non-streaming chat with messages and tools attributes")
print("=" * 80)

client = OpenAI()

# Define a tool
tools = [
    {
        "type": "function",
        "function": {
            "name": "get_weather",
            "description": "Get the current weather in a location",
            "parameters": {
                "type": "object",
                "properties": {
                    "location": {
                        "type": "string",
                        "description": "The city and state, e.g. San Francisco, CA",
                    },
                },
                "required": ["location"],
            },
        },
    }
]

messages = [
    {"role": "system", "content": "You are a helpful assistant."},
    {"role": "user", "content": "What's the weather like in Boston?"},
]

try:
    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=messages,
        tools=tools,
        stream=False,
    )
    
    print(f"\nResponse: {response.choices[0].message.content}")
    print("\nCheck the trace output above for:")
    print("  - gen_ai.input.messages: JSON array of input messages")
    print("  - gen_ai.output.messages: JSON array of output messages")
    print("  - gen_ai.input.tools: JSON array of tool definitions")
    
except Exception as e:
    print(f"Error: {e}")
    print("Note: This example requires a valid OPENAI_API_KEY environment variable")

# Example 2: Streaming chat to demonstrate timing metrics
print("\n" + "=" * 80)
print("Example 2: Streaming chat to demonstrate timing metrics")
print("=" * 80)

messages_streaming = [
    {"role": "user", "content": "Write a short poem about OpenTelemetry."},
]

try:
    stream = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=messages_streaming,
        stream=True,
    )
    
    print("\nStreaming response:")
    for chunk in stream:
        if chunk.choices and chunk.choices[0].delta.content:
            print(chunk.choices[0].delta.content, end="", flush=True)
    
    print("\n\nCheck the metrics output for:")
    print("  - gen_ai.client.time_to_first_token: Time until first token")
    print("  - gen_ai.client.time_per_output_token: Average time per token")
    print("  - gen_ai.client.time_between_token: Time between consecutive tokens")
    print("  - gen_ai.client.operation: Overall operation duration")
    
except Exception as e:
    print(f"Error: {e}")
    print("Note: This example requires a valid OPENAI_API_KEY environment variable")

# Example 3: Request with cached tokens (requires prompt caching enabled)
print("\n" + "=" * 80)
print("Example 3: Cached tokens metric")
print("=" * 80)
print("Note: Cached tokens are reported when prompt caching is enabled")
print("Check gen_ai.usage.prompt_tokens_details.cached_tokens metric")

# Uninstrument
OpenAIInstrumentor().uninstrument()

print("\n" + "=" * 80)
print("Demo complete!")
print("=" * 80)
