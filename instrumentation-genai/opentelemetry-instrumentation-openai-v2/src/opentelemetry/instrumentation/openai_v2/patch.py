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


from timeit import default_timer
from typing import Any, Optional

from openai import Stream

from opentelemetry._logs import Logger, LogRecord
from opentelemetry.context import get_current
from opentelemetry.semconv._incubating.attributes import (
    gen_ai_attributes as GenAIAttributes,
)
from opentelemetry.semconv._incubating.attributes import (
    server_attributes as ServerAttributes,
)
from opentelemetry.trace import Span, SpanKind, Tracer
from opentelemetry.trace.propagation import set_span_in_context

from .instruments import Instruments
from .utils import (
    choice_to_event,
    get_llm_request_attributes,
    handle_span_exception,
    is_streaming,
    message_to_event,
    messages_to_json,
    set_span_attribute,
    tools_to_json,
)

# Define attribute names for input/output messages and tools
GEN_AI_INPUT_MESSAGES = getattr(
    GenAIAttributes, "GEN_AI_INPUT_MESSAGES", "gen_ai.input.messages"
)
GEN_AI_OUTPUT_MESSAGES = getattr(
    GenAIAttributes, "GEN_AI_OUTPUT_MESSAGES", "gen_ai.output.messages"
)
GEN_AI_INPUT_TOOLS = getattr(
    GenAIAttributes, "GEN_AI_INPUT_TOOLS", "gen_ai.input.tools"
)


def chat_completions_create(
    tracer: Tracer,
    logger: Logger,
    instruments: Instruments,
    capture_content: bool,
):
    """Wrap the `create` method of the `ChatCompletion` class to trace it."""

    def traced_method(wrapped, instance, args, kwargs):
        span_attributes = {**get_llm_request_attributes(kwargs, instance)}

        span_name = f"{span_attributes[GenAIAttributes.GEN_AI_OPERATION_NAME]} {span_attributes[GenAIAttributes.GEN_AI_REQUEST_MODEL]}"
        with tracer.start_as_current_span(
            name=span_name,
            kind=SpanKind.CLIENT,
            attributes=span_attributes,
            end_on_exit=False,
        ) as span:
            # Add input messages attribute
            messages = kwargs.get("messages", [])
            if messages and span.is_recording():
                input_messages_json = messages_to_json(messages, capture_content)
                set_span_attribute(span, GEN_AI_INPUT_MESSAGES, input_messages_json)

            # Add tools attribute
            tools = kwargs.get("tools", [])
            if tools and span.is_recording():
                tools_json = tools_to_json(tools)
                if tools_json:
                    set_span_attribute(span, GEN_AI_INPUT_TOOLS, tools_json)

            for message in messages:
                logger.emit(message_to_event(message, capture_content))

            start = default_timer()
            result = None
            error_type = None
            try:
                result = wrapped(*args, **kwargs)
                if hasattr(result, "parse"):
                    # result is of type LegacyAPIResponse, call parse to get the actual response
                    parsed_result = result.parse()
                else:
                    parsed_result = result
                if is_streaming(kwargs):
                    return StreamWrapper(
                        parsed_result, span, logger, capture_content, instruments, span_attributes, start
                    )

                if span.is_recording():
                    _set_response_attributes(
                        span, parsed_result, logger, capture_content
                    )
                for choice in getattr(parsed_result, "choices", []):
                    logger.emit(choice_to_event(choice, capture_content))

                span.end()
                return result

            except Exception as error:
                error_type = type(error).__qualname__
                handle_span_exception(span, error)
                raise
            finally:
                duration = max((default_timer() - start), 0)
                _record_metrics(
                    instruments,
                    duration,
                    result,
                    span_attributes,
                    error_type,
                    GenAIAttributes.GenAiOperationNameValues.CHAT.value,
                )

    return traced_method


def async_chat_completions_create(
    tracer: Tracer,
    logger: Logger,
    instruments: Instruments,
    capture_content: bool,
):
    """Wrap the `create` method of the `AsyncChatCompletion` class to trace it."""

    async def traced_method(wrapped, instance, args, kwargs):
        span_attributes = {**get_llm_request_attributes(kwargs, instance)}

        span_name = f"{span_attributes[GenAIAttributes.GEN_AI_OPERATION_NAME]} {span_attributes[GenAIAttributes.GEN_AI_REQUEST_MODEL]}"
        with tracer.start_as_current_span(
            name=span_name,
            kind=SpanKind.CLIENT,
            attributes=span_attributes,
            end_on_exit=False,
        ) as span:
            # Add input messages attribute
            messages = kwargs.get("messages", [])
            if messages and span.is_recording():
                input_messages_json = messages_to_json(messages, capture_content)
                set_span_attribute(span, GEN_AI_INPUT_MESSAGES, input_messages_json)

            # Add tools attribute
            tools = kwargs.get("tools", [])
            if tools and span.is_recording():
                tools_json = tools_to_json(tools)
                if tools_json:
                    set_span_attribute(span, GEN_AI_INPUT_TOOLS, tools_json)

            for message in messages:
                logger.emit(message_to_event(message, capture_content))

            start = default_timer()
            result = None
            error_type = None
            try:
                result = await wrapped(*args, **kwargs)
                if hasattr(result, "parse"):
                    # result is of type LegacyAPIResponse, calling parse to get the actual response
                    parsed_result = result.parse()
                else:
                    parsed_result = result
                if is_streaming(kwargs):
                    return StreamWrapper(
                        parsed_result, span, logger, capture_content, instruments, span_attributes, start
                    )

                if span.is_recording():
                    _set_response_attributes(
                        span, parsed_result, logger, capture_content
                    )
                for choice in getattr(parsed_result, "choices", []):
                    logger.emit(choice_to_event(choice, capture_content))

                span.end()
                return result

            except Exception as error:
                error_type = type(error).__qualname__
                handle_span_exception(span, error)
                raise
            finally:
                duration = max((default_timer() - start), 0)
                _record_metrics(
                    instruments,
                    duration,
                    result,
                    span_attributes,
                    error_type,
                    GenAIAttributes.GenAiOperationNameValues.CHAT.value,
                )

    return traced_method


def embeddings_create(
    tracer: Tracer,
    instruments: Instruments,
    capture_content: bool,
):
    """Wrap the `create` method of the `Embeddings` class to trace it."""

    def traced_method(wrapped, instance, args, kwargs):
        span_attributes = get_llm_request_attributes(
            kwargs,
            instance,
            GenAIAttributes.GenAiOperationNameValues.EMBEDDINGS.value,
        )
        span_name = _get_embeddings_span_name(span_attributes)
        input_text = kwargs.get("input", "")

        with tracer.start_as_current_span(
            name=span_name,
            kind=SpanKind.CLIENT,
            attributes=span_attributes,
            end_on_exit=True,
        ) as span:
            start = default_timer()
            result = None
            error_type = None

            try:
                result = wrapped(*args, **kwargs)

                if span.is_recording():
                    _set_embeddings_response_attributes(
                        span, result, capture_content, input_text
                    )

                return result

            except Exception as error:
                error_type = type(error).__qualname__
                handle_span_exception(span, error)
                raise

            finally:
                duration = max((default_timer() - start), 0)
                _record_metrics(
                    instruments,
                    duration,
                    result,
                    span_attributes,
                    error_type,
                    GenAIAttributes.GenAiOperationNameValues.EMBEDDINGS.value,
                )

    return traced_method


def async_embeddings_create(
    tracer: Tracer,
    instruments: Instruments,
    capture_content: bool,
):
    """Wrap the `create` method of the `AsyncEmbeddings` class to trace it."""

    async def traced_method(wrapped, instance, args, kwargs):
        span_attributes = get_llm_request_attributes(
            kwargs,
            instance,
            GenAIAttributes.GenAiOperationNameValues.EMBEDDINGS.value,
        )
        span_name = _get_embeddings_span_name(span_attributes)
        input_text = kwargs.get("input", "")

        with tracer.start_as_current_span(
            name=span_name,
            kind=SpanKind.CLIENT,
            attributes=span_attributes,
            end_on_exit=True,
        ) as span:
            start = default_timer()
            result = None
            error_type = None

            try:
                result = await wrapped(*args, **kwargs)

                if span.is_recording():
                    _set_embeddings_response_attributes(
                        span, result, capture_content, input_text
                    )

                return result

            except Exception as error:
                error_type = type(error).__qualname__
                handle_span_exception(span, error)
                raise

            finally:
                duration = max((default_timer() - start), 0)
                _record_metrics(
                    instruments,
                    duration,
                    result,
                    span_attributes,
                    error_type,
                    GenAIAttributes.GenAiOperationNameValues.EMBEDDINGS.value,
                )

    return traced_method


def _get_embeddings_span_name(span_attributes):
    """Get span name for embeddings operations."""
    return f"{span_attributes[GenAIAttributes.GEN_AI_OPERATION_NAME]} {span_attributes[GenAIAttributes.GEN_AI_REQUEST_MODEL]}"


def _record_metrics(
    instruments: Instruments,
    duration: float,
    result,
    request_attributes: dict,
    error_type: Optional[str],
    operation_name: str,
):
    common_attributes = {
        GenAIAttributes.GEN_AI_OPERATION_NAME: operation_name,
        GenAIAttributes.GEN_AI_SYSTEM: GenAIAttributes.GenAiSystemValues.OPENAI.value,
        GenAIAttributes.GEN_AI_REQUEST_MODEL: request_attributes[
            GenAIAttributes.GEN_AI_REQUEST_MODEL
        ],
    }

    if "gen_ai.embeddings.dimension.count" in request_attributes:
        common_attributes["gen_ai.embeddings.dimension.count"] = (
            request_attributes["gen_ai.embeddings.dimension.count"]
        )

    if error_type:
        common_attributes["error.type"] = error_type

    if result and getattr(result, "model", None):
        common_attributes[GenAIAttributes.GEN_AI_RESPONSE_MODEL] = result.model

    if result and getattr(result, "service_tier", None):
        common_attributes[
            GenAIAttributes.GEN_AI_OPENAI_RESPONSE_SERVICE_TIER
        ] = result.service_tier

    if result and getattr(result, "system_fingerprint", None):
        common_attributes["gen_ai.openai.response.system_fingerprint"] = (
            result.system_fingerprint
        )

    if ServerAttributes.SERVER_ADDRESS in request_attributes:
        common_attributes[ServerAttributes.SERVER_ADDRESS] = (
            request_attributes[ServerAttributes.SERVER_ADDRESS]
        )

    if ServerAttributes.SERVER_PORT in request_attributes:
        common_attributes[ServerAttributes.SERVER_PORT] = request_attributes[
            ServerAttributes.SERVER_PORT
        ]

    instruments.operation_duration_histogram.record(
        duration,
        attributes=common_attributes,
    )

    if result and getattr(result, "usage", None):
        # Always record input tokens
        input_attributes = {
            **common_attributes,
            GenAIAttributes.GEN_AI_TOKEN_TYPE: GenAIAttributes.GenAiTokenTypeValues.INPUT.value,
        }
        instruments.token_usage_histogram.record(
            result.usage.prompt_tokens,
            attributes=input_attributes,
        )

        # Record cached tokens if available
        if hasattr(result.usage, "prompt_tokens_details") and result.usage.prompt_tokens_details:
            cached_tokens = getattr(result.usage.prompt_tokens_details, "cached_tokens", None)
            if cached_tokens is not None:
                instruments.cached_tokens_histogram.record(
                    cached_tokens,
                    attributes=common_attributes,
                )

        # For embeddings, don't record output tokens as all tokens are input tokens
        if (
            operation_name
            != GenAIAttributes.GenAiOperationNameValues.EMBEDDINGS.value
        ):
            output_attributes = {
                **common_attributes,
                GenAIAttributes.GEN_AI_TOKEN_TYPE: GenAIAttributes.GenAiTokenTypeValues.COMPLETION.value,
            }
            instruments.token_usage_histogram.record(
                result.usage.completion_tokens, attributes=output_attributes
            )


def _set_response_attributes(
    span, result, logger: Logger, capture_content: bool
):
    if getattr(result, "model", None):
        set_span_attribute(
            span, GenAIAttributes.GEN_AI_RESPONSE_MODEL, result.model
        )

    if getattr(result, "choices", None):
        finish_reasons = []
        output_messages = []
        
        for choice in result.choices:
            finish_reasons.append(choice.finish_reason or "error")
            
            # Build output message for this choice
            if choice.message:
                message_dict = {"role": "assistant"}
                if capture_content and getattr(choice.message, "content", None):
                    message_dict["content"] = choice.message.content
                
                # Handle tool calls in the output message
                if getattr(choice.message, "tool_calls", None):
                    tool_calls = []
                    for tool_call in choice.message.tool_calls:
                        tc_dict = {"id": tool_call.id, "type": "function"}
                        func_dict = {"name": tool_call.function.name}
                        if capture_content and tool_call.function.arguments:
                            func_dict["arguments"] = tool_call.function.arguments.replace("\n", "")
                        tc_dict["function"] = func_dict
                        tool_calls.append(tc_dict)
                    message_dict["tool_calls"] = tool_calls
                
                output_messages.append(message_dict)
        
        # Set output messages attribute
        if output_messages:
            import json
            set_span_attribute(
                span,
                GEN_AI_OUTPUT_MESSAGES,
                json.dumps(output_messages, ensure_ascii=False),
            )

        set_span_attribute(
            span,
            GenAIAttributes.GEN_AI_RESPONSE_FINISH_REASONS,
            finish_reasons,
        )

    if getattr(result, "id", None):
        set_span_attribute(span, GenAIAttributes.GEN_AI_RESPONSE_ID, result.id)

    if getattr(result, "service_tier", None):
        set_span_attribute(
            span,
            GenAIAttributes.GEN_AI_OPENAI_RESPONSE_SERVICE_TIER,
            result.service_tier,
        )

    # Get the usage
    if getattr(result, "usage", None):
        set_span_attribute(
            span,
            GenAIAttributes.GEN_AI_USAGE_INPUT_TOKENS,
            result.usage.prompt_tokens,
        )
        set_span_attribute(
            span,
            GenAIAttributes.GEN_AI_USAGE_OUTPUT_TOKENS,
            result.usage.completion_tokens,
        )


def _set_embeddings_response_attributes(
    span: Span,
    result: Any,
    capture_content: bool,
    input_text: str,
):
    set_span_attribute(
        span, GenAIAttributes.GEN_AI_RESPONSE_MODEL, result.model
    )

    # Set embeddings dimensions if we can determine it from the response
    if getattr(result, "data", None) and len(result.data) > 0:
        first_embedding = result.data[0]
        if getattr(first_embedding, "embedding", None):
            set_span_attribute(
                span,
                "gen_ai.embeddings.dimension.count",
                len(first_embedding.embedding),
            )

    # Get the usage
    if getattr(result, "usage", None):
        set_span_attribute(
            span,
            GenAIAttributes.GEN_AI_USAGE_INPUT_TOKENS,
            result.usage.prompt_tokens,
        )
        # Don't set output tokens for embeddings as all tokens are input tokens


class ToolCallBuffer:
    def __init__(self, index, tool_call_id, function_name):
        self.index = index
        self.function_name = function_name
        self.tool_call_id = tool_call_id
        self.arguments = []

    def append_arguments(self, arguments):
        self.arguments.append(arguments)


class ChoiceBuffer:
    def __init__(self, index):
        self.index = index
        self.finish_reason = None
        self.text_content = []
        self.tool_calls_buffers = []

    def append_text_content(self, content):
        self.text_content.append(content)

    def append_tool_call(self, tool_call):
        idx = tool_call.index
        # make sure we have enough tool call buffers
        for _ in range(len(self.tool_calls_buffers), idx + 1):
            self.tool_calls_buffers.append(None)

        if not self.tool_calls_buffers[idx]:
            self.tool_calls_buffers[idx] = ToolCallBuffer(
                idx, tool_call.id, tool_call.function.name
            )
        self.tool_calls_buffers[idx].append_arguments(
            tool_call.function.arguments
        )


class StreamWrapper:
    span: Span
    response_id: Optional[str] = None
    response_model: Optional[str] = None
    service_tier: Optional[str] = None
    finish_reasons: list = []
    prompt_tokens: Optional[int] = None
    completion_tokens: Optional[int] = None
    cached_tokens: Optional[int] = None
    system_fingerprint: Optional[str] = None

    def __init__(
        self,
        stream: Stream,
        span: Span,
        logger: Logger,
        capture_content: bool,
        instruments: Instruments,
        span_attributes: dict,
        start_time: float,
    ):
        self.stream = stream
        self.span = span
        self.choice_buffers = []
        self._span_started = False
        self.capture_content = capture_content
        self.instruments = instruments
        self.span_attributes = span_attributes
        self.start_time = start_time
        
        # Timing metrics for streaming
        self.first_token_time = None
        self.last_token_time = None
        self.token_times = []
        self.token_count = 0

        self.logger = logger
        self.setup()

    def setup(self):
        if not self._span_started:
            self._span_started = True

    def cleanup(self):
        if self._span_started:
            if self.span.is_recording():
                if self.response_model:
                    set_span_attribute(
                        self.span,
                        GenAIAttributes.GEN_AI_RESPONSE_MODEL,
                        self.response_model,
                    )

                if self.response_id:
                    set_span_attribute(
                        self.span,
                        GenAIAttributes.GEN_AI_RESPONSE_ID,
                        self.response_id,
                    )

                set_span_attribute(
                    self.span,
                    GenAIAttributes.GEN_AI_USAGE_INPUT_TOKENS,
                    self.prompt_tokens,
                )
                set_span_attribute(
                    self.span,
                    GenAIAttributes.GEN_AI_USAGE_OUTPUT_TOKENS,
                    self.completion_tokens,
                )

                set_span_attribute(
                    self.span,
                    GenAIAttributes.GEN_AI_OPENAI_RESPONSE_SERVICE_TIER,
                    self.service_tier,
                )

                set_span_attribute(
                    self.span,
                    GenAIAttributes.GEN_AI_RESPONSE_FINISH_REASONS,
                    self.finish_reasons,
                )

            # Build and set output messages
            output_messages = []
            for idx, choice in enumerate(self.choice_buffers):
                message = {"role": "assistant"}
                if self.capture_content and choice.text_content:
                    message["content"] = "".join(choice.text_content)
                if choice.tool_calls_buffers:
                    tool_calls = []
                    for tool_call in choice.tool_calls_buffers:
                        function = {"name": tool_call.function_name}
                        if self.capture_content:
                            function["arguments"] = "".join(
                                tool_call.arguments
                            )
                        tool_call_dict = {
                            "id": tool_call.tool_call_id,
                            "type": "function",
                            "function": function,
                        }
                        tool_calls.append(tool_call_dict)
                    message["tool_calls"] = tool_calls

                output_messages.append(message)

                body = {
                    "index": idx,
                    "finish_reason": choice.finish_reason or "error",
                    "message": message,
                }

                event_attributes = {
                    GenAIAttributes.GEN_AI_SYSTEM: GenAIAttributes.GenAiSystemValues.OPENAI.value
                }
                context = set_span_in_context(self.span, get_current())
                self.logger.emit(
                    LogRecord(
                        event_name="gen_ai.choice",
                        attributes=event_attributes,
                        body=body,
                        context=context,
                    )
                )

            # Set output messages attribute
            if output_messages and self.span.is_recording():
                import json
                set_span_attribute(
                    self.span,
                    GEN_AI_OUTPUT_MESSAGES,
                    json.dumps(output_messages, ensure_ascii=False),
                )

            # Record timing metrics for streaming
            if self.first_token_time and self.instruments:
                common_attributes = {
                    GenAIAttributes.GEN_AI_OPERATION_NAME: GenAIAttributes.GenAiOperationNameValues.CHAT.value,
                    GenAIAttributes.GEN_AI_SYSTEM: GenAIAttributes.GenAiSystemValues.OPENAI.value,
                    GenAIAttributes.GEN_AI_REQUEST_MODEL: self.span_attributes.get(
                        GenAIAttributes.GEN_AI_REQUEST_MODEL
                    ),
                }

                if self.response_model:
                    common_attributes[GenAIAttributes.GEN_AI_RESPONSE_MODEL] = self.response_model

                # Time to first token
                time_to_first_token = self.first_token_time - self.start_time
                self.instruments.time_to_first_token_histogram.record(
                    time_to_first_token, attributes=common_attributes
                )

                # Time per output token (average)
                if self.token_count > 0 and self.last_token_time:
                    total_token_time = self.last_token_time - self.first_token_time
                    time_per_token = total_token_time / self.token_count
                    self.instruments.time_per_output_token_histogram.record(
                        time_per_token, attributes=common_attributes
                    )

                # Time between tokens (average)
                if len(self.token_times) > 1:
                    for i in range(1, len(self.token_times)):
                        time_between = self.token_times[i] - self.token_times[i - 1]
                        self.instruments.time_between_token_histogram.record(
                            time_between, attributes=common_attributes
                        )

                # Operation duration
                if self.last_token_time:
                    operation_duration = self.last_token_time - self.start_time
                    self.instruments.operation_histogram.record(
                        operation_duration, attributes=common_attributes
                    )

            # Record token usage metrics for streaming
            if self.prompt_tokens is not None or self.completion_tokens is not None:
                token_common_attributes = {
                    GenAIAttributes.GEN_AI_OPERATION_NAME: GenAIAttributes.GenAiOperationNameValues.CHAT.value,
                    GenAIAttributes.GEN_AI_SYSTEM: GenAIAttributes.GenAiSystemValues.OPENAI.value,
                    GenAIAttributes.GEN_AI_REQUEST_MODEL: self.span_attributes.get(
                        GenAIAttributes.GEN_AI_REQUEST_MODEL
                    ),
                }

                if self.response_model:
                    token_common_attributes[GenAIAttributes.GEN_AI_RESPONSE_MODEL] = self.response_model

                if self.service_tier:
                    token_common_attributes[GenAIAttributes.GEN_AI_OPENAI_RESPONSE_SERVICE_TIER] = self.service_tier

                if self.system_fingerprint:
                    token_common_attributes["gen_ai.openai.response.system_fingerprint"] = self.system_fingerprint

                # Add server attributes from span_attributes
                if ServerAttributes.SERVER_ADDRESS in self.span_attributes:
                    token_common_attributes[ServerAttributes.SERVER_ADDRESS] = self.span_attributes[ServerAttributes.SERVER_ADDRESS]

                if ServerAttributes.SERVER_PORT in self.span_attributes:
                    token_common_attributes[ServerAttributes.SERVER_PORT] = self.span_attributes[ServerAttributes.SERVER_PORT]

                # Record input tokens
                if self.prompt_tokens is not None:
                    input_attributes = {
                        **token_common_attributes,
                        GenAIAttributes.GEN_AI_TOKEN_TYPE: GenAIAttributes.GenAiTokenTypeValues.INPUT.value,
                    }
                    self.instruments.token_usage_histogram.record(
                        self.prompt_tokens,
                        attributes=input_attributes,
                    )

                # Record output tokens
                if self.completion_tokens is not None:
                    output_attributes = {
                        **token_common_attributes,
                        GenAIAttributes.GEN_AI_TOKEN_TYPE: GenAIAttributes.GenAiTokenTypeValues.COMPLETION.value,
                    }
                    self.instruments.token_usage_histogram.record(
                        self.completion_tokens,
                        attributes=output_attributes,
                    )

                # Record cached tokens if available
                if self.cached_tokens is not None:
                    self.instruments.cached_tokens_histogram.record(
                        self.cached_tokens,
                        attributes=token_common_attributes,
                    )

            self.span.end()
            self._span_started = False

    def __enter__(self):
        self.setup()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        try:
            if exc_type is not None:
                handle_span_exception(self.span, exc_val)
        finally:
            self.cleanup()
        return False  # Propagate the exception

    async def __aenter__(self):
        self.setup()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        try:
            if exc_type is not None:
                handle_span_exception(self.span, exc_val)
        finally:
            self.cleanup()
        return False  # Propagate the exception

    def close(self):
        self.stream.close()
        self.cleanup()

    def __iter__(self):
        return self

    def __aiter__(self):
        return self

    def __next__(self):
        try:
            chunk = next(self.stream)
            self.process_chunk(chunk)
            return chunk
        except StopIteration:
            self.cleanup()
            raise
        except Exception as error:
            handle_span_exception(self.span, error)
            self.cleanup()
            raise

    async def __anext__(self):
        try:
            chunk = await self.stream.__anext__()
            self.process_chunk(chunk)
            return chunk
        except StopAsyncIteration:
            self.cleanup()
            raise
        except Exception as error:
            handle_span_exception(self.span, error)
            self.cleanup()
            raise

    def set_response_model(self, chunk):
        if self.response_model:
            return

        if getattr(chunk, "model", None):
            self.response_model = chunk.model

    def set_response_id(self, chunk):
        if self.response_id:
            return

        if getattr(chunk, "id", None):
            self.response_id = chunk.id

    def set_response_service_tier(self, chunk):
        if self.service_tier:
            return

        if getattr(chunk, "service_tier", None):
            self.service_tier = chunk.service_tier

    def set_system_fingerprint(self, chunk):
        if self.system_fingerprint:
            return

        if getattr(chunk, "system_fingerprint", None):
            self.system_fingerprint = chunk.system_fingerprint

    def build_streaming_response(self, chunk):
        if getattr(chunk, "choices", None) is None:
            return

        choices = chunk.choices
        has_content = False
        
        for choice in choices:
            if not choice.delta:
                continue

            # make sure we have enough choice buffers
            for idx in range(len(self.choice_buffers), choice.index + 1):
                self.choice_buffers.append(ChoiceBuffer(idx))

            if choice.finish_reason:
                self.choice_buffers[
                    choice.index
                ].finish_reason = choice.finish_reason

            if choice.delta.content is not None:
                self.choice_buffers[choice.index].append_text_content(
                    choice.delta.content
                )
                has_content = True

            if choice.delta.tool_calls is not None:
                for tool_call in choice.delta.tool_calls:
                    self.choice_buffers[choice.index].append_tool_call(
                        tool_call
                    )
                has_content = True

        # Track token timing for content chunks
        if has_content:
            current_time = default_timer()
            if self.first_token_time is None:
                self.first_token_time = current_time
            self.last_token_time = current_time
            self.token_times.append(current_time)
            self.token_count += 1

    def set_usage(self, chunk):
        if getattr(chunk, "usage", None):
            self.completion_tokens = chunk.usage.completion_tokens
            self.prompt_tokens = chunk.usage.prompt_tokens
            # Capture cached tokens if available
            if hasattr(chunk.usage, "prompt_tokens_details") and chunk.usage.prompt_tokens_details:
                self.cached_tokens = getattr(chunk.usage.prompt_tokens_details, "cached_tokens", None)

    def process_chunk(self, chunk):
        self.set_response_id(chunk)
        self.set_response_model(chunk)
        self.set_response_service_tier(chunk)
        self.set_system_fingerprint(chunk)
        self.build_streaming_response(chunk)
        self.set_usage(chunk)

    def parse(self):
        """Called when using with_raw_response with stream=True"""
        return self
