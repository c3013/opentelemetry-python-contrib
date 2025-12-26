# New Trace Attributes and Metrics

This document describes the new trace attributes and metrics added to the OpenAI v2 instrumentation.

## New Trace Attributes

### gen_ai.input.messages

A JSON-encoded array of input messages sent to the LLM. Each message includes:
- `role`: The role of the message sender (e.g., "user", "system", "assistant", "tool")
- `content`: The message content (only included when `OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT=true`)
- `tool_calls`: Array of tool calls (for assistant messages with tool calls)
- `tool_call_id`: The tool call ID (for tool role messages)

**Example:**
```json
[
  {
    "role": "system",
    "content": "You are a helpful assistant."
  },
  {
    "role": "user",
    "content": "What's the weather in Boston?"
  }
]
```

### gen_ai.output.messages

A JSON-encoded array of output messages received from the LLM. Each message includes:
- `role`: Always "assistant"
- `content`: The generated text content (only included when `OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT=true`)
- `tool_calls`: Array of tool calls if the assistant is calling tools

**Example:**
```json
[
  {
    "role": "assistant",
    "content": "I'll check the weather for you.",
    "tool_calls": [
      {
        "id": "call_abc123",
        "type": "function",
        "function": {
          "name": "get_weather",
          "arguments": "{\"location\": \"Boston, MA\"}"
        }
      }
    ]
  }
]
```

### gen_ai.input.tools

A JSON-encoded array of tool definitions available to the LLM. Each tool includes:
- `type`: The type of tool (typically "function")
- `function`: Object containing:
  - `name`: The function name
  - `description`: The function description

Note: The `parameters` field is intentionally omitted from the trace to avoid excessively large span attributes.

**Example:**
```json
[
  {
    "type": "function",
    "function": {
      "name": "get_weather",
      "description": "Get the current weather in a location"
    }
  }
]
```

## New Metrics

All new metrics are histograms that record timing and token information.

### gen_ai.client.time_to_first_token

**Type:** Histogram  
**Unit:** seconds (s)  
**Description:** Time elapsed from the start of the request until the first token is received in a streaming response.

**Attributes:**
- `gen_ai.operation.name`: "chat"
- `gen_ai.system`: "openai"
- `gen_ai.request.model`: The requested model
- `gen_ai.response.model`: The actual model used (if available)

### gen_ai.client.time_per_output_token

**Type:** Histogram  
**Unit:** seconds (s)  
**Description:** Average time per output token in a streaming response. Calculated as: (time_of_last_token - time_of_first_token) / number_of_tokens

**Attributes:**
- `gen_ai.operation.name`: "chat"
- `gen_ai.system`: "openai"
- `gen_ai.request.model`: The requested model
- `gen_ai.response.model`: The actual model used (if available)

### gen_ai.client.time_between_token

**Type:** Histogram  
**Unit:** seconds (s)  
**Description:** Time between consecutive tokens in a streaming response. Multiple measurements are recorded for a single request.

**Attributes:**
- `gen_ai.operation.name`: "chat"
- `gen_ai.system`: "openai"
- `gen_ai.request.model`: The requested model
- `gen_ai.response.model`: The actual model used (if available)

### gen_ai.client.operation

**Type:** Histogram  
**Unit:** seconds (s)  
**Description:** Total duration of the streaming operation from start to the last token received.

**Attributes:**
- `gen_ai.operation.name`: "chat"
- `gen_ai.system`: "openai"
- `gen_ai.request.model`: The requested model
- `gen_ai.response.model`: The actual model used (if available)

### gen_ai.usage.prompt_tokens_details.cached_tokens

**Type:** Histogram  
**Unit:** tokens ({token})  
**Description:** Number of tokens in the prompt that were served from the cache. Only recorded when the OpenAI API returns cached token information (requires prompt caching to be enabled).

**Attributes:**
- `gen_ai.operation.name`: "chat" or "embeddings"
- `gen_ai.system`: "openai"
- `gen_ai.request.model`: The requested model
- `gen_ai.response.model`: The actual model used (if available)

## Usage

### Enabling Message Content Capture

To capture message content in the trace attributes, set the environment variable:

```bash
export OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT=true
```

When disabled (default), only roles and structure are captured, not the actual content.

### Example Code

```python
import os
from openai import OpenAI
from opentelemetry.instrumentation.openai_v2 import OpenAIInstrumentor

# Enable content capture
os.environ["OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT"] = "true"

# Instrument OpenAI
OpenAIInstrumentor().instrument()

client = OpenAI()

# Non-streaming request with tools
tools = [{
    "type": "function",
    "function": {
        "name": "get_weather",
        "description": "Get weather for a location",
    }
}]

response = client.chat.completions.create(
    model="gpt-4o-mini",
    messages=[
        {"role": "user", "content": "What's the weather in Boston?"}
    ],
    tools=tools,
)

# Streaming request
stream = client.chat.completions.create(
    model="gpt-4o-mini",
    messages=[
        {"role": "user", "content": "Tell me a story."}
    ],
    stream=True,
)

for chunk in stream:
    if chunk.choices and chunk.choices[0].delta.content:
        print(chunk.choices[0].delta.content, end="")
```

## Notes

- The `gen_ai.input.messages` and `gen_ai.output.messages` attributes are captured for both streaming and non-streaming requests.
- The `gen_ai.input.tools` attribute is only present when tools are provided in the request.
- Timing metrics (time_to_first_token, time_per_output_token, etc.) are only recorded for streaming responses.
- The cached tokens metric is only recorded when the API returns `prompt_tokens_details.cached_tokens` in the usage information.
