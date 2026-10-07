"""Execute the upstream hermetic tool agent, preserving its real graph and tool node."""
import importlib.util
import os
from pathlib import Path
from langchain_core.messages import AIMessage, ToolMessage
from langchain_core.outputs import ChatGeneration, ChatResult

source = Path(os.environ['WRAITH_EXTERNAL_SOURCE'])
spec = importlib.util.spec_from_file_location('upstream_tools', source)
upstream = importlib.util.module_from_spec(spec)
spec.loader.exec_module(upstream)
if os.environ.get('WRAITH_EXTERNAL_VARIANT') == 'skip-tool':
    def skip(self, messages, **kwargs):
        return ChatResult(generations=[ChatGeneration(message=AIMessage(content='done.'))])
    upstream._ToolBindingFakeChatModel._generate = skip


def evaluate(input, context):
    result = upstream.graph.invoke({'messages': [('user', input['text'])]})
    calls = {}
    for message in result['messages']:
        if isinstance(message, AIMessage):
            calls.update({call['id']: call for call in message.tool_calls})
        if isinstance(message, ToolMessage):
            call = calls[message.tool_call_id]
            context.tool(call['name'], call['args'], message.content, message.status != 'error')
    return {'text': result['messages'][-1].content}
