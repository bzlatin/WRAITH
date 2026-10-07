"""Run the unmodified upstream weather agent with offline model/HTTP boundaries."""
import importlib.util
import os
from pathlib import Path
import logfire
import httpx
from pydantic_ai import models
from pydantic_ai.messages import ModelResponse, TextPart, ToolCallPart, ToolReturnPart
from pydantic_ai.models.function import FunctionModel

models.ALLOW_MODEL_REQUESTS = False
# The upstream example enables Logfire automatically. Force it local before import.
configure = logfire.configure
logfire.configure = lambda *args, **kwargs: configure(send_to_logfire=False, console=False)
os.environ['OPENAI_API_KEY'] = 'offline-placeholder-never-sent'
source = Path(os.environ['WRAITH_EXTERNAL_SOURCE'])
spec = importlib.util.spec_from_file_location('upstream_weather', source)
upstream = importlib.util.module_from_spec(spec)
import sys
sys.modules[spec.name] = upstream
spec.loader.exec_module(upstream)


async def evaluate(input, context):
    location = input['city']
    temperature = input['temperature']
    def transport(request):
        endpoint = request.url.path
        if endpoint == '/latlng': return httpx.Response(200, json={'lat': 51.5, 'lng': -0.1})
        if endpoint == '/number': return httpx.Response(200, text=str(temperature))
        if endpoint == '/weather': return httpx.Response(200, text='Sunny')
        raise AssertionError(f'Unexpected HTTP fixture request: {endpoint}')
    def model(messages, info):
        returns = [part for message in messages for part in message.parts if isinstance(part, ToolReturnPart)]
        if os.environ.get('WRAITH_EXTERNAL_VARIANT') == 'skip-tool':
            return ModelResponse(parts=[TextPart(f'{location}: weather unavailable.')])
        if not returns:
            return ModelResponse(parts=[ToolCallPart('get_lat_lng', {'location_description': location}, 'coordinates')])
        weather = next((part.content for part in returns if part.tool_name == 'get_weather'), None)
        if weather is None:
            return ModelResponse(parts=[ToolCallPart('get_weather', {'lat': 51.5, 'lng': -0.1}, 'forecast')])
        return ModelResponse(parts=[TextPart(f"{location}: {weather['temperature']}, {weather['description']}.")])
    async with httpx.AsyncClient(transport=httpx.MockTransport(transport)) as client:
        with upstream.weather_agent.override(model=FunctionModel(model)):
            result = await upstream.weather_agent.run(f'Weather in {location}?', deps=upstream.Deps(client=client))
    arguments = {}
    for message in result.all_messages():
        for part in message.parts:
            if isinstance(part, ToolCallPart): arguments[part.tool_call_id] = part.args_as_dict()
            if isinstance(part, ToolReturnPart): context.tool(part.tool_name, arguments.get(part.tool_call_id), part.content.model_dump(mode='json') if hasattr(part.content, 'model_dump') else part.content)
    return {'text': result.output}
