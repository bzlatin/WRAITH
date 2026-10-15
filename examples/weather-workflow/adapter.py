"""Observe the actual upstream weather tools with scripted model/HTTP boundaries."""

import importlib.util
import os
from pathlib import Path
import sys

import httpx
import logfire
from pydantic_ai import capture_run_messages, models
from pydantic_ai.messages import ModelResponse, TextPart, ToolCallPart, ToolReturnPart
from pydantic_ai.models.function import FunctionModel

models.ALLOW_MODEL_REQUESTS = False
# The source example configures Logfire on import. Keep every export disabled.
configure = logfire.configure
logfire.configure = lambda *args, **kwargs: configure(
    send_to_logfire=False, console=False
)

os.environ["OPENAI_API_KEY"] = "offline-placeholder-never-sent"
spec = importlib.util.spec_from_file_location(
    "weather_application", Path.cwd() / "weather_agent.py"
)
app = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = app
spec.loader.exec_module(app)


async def evaluate(payload, context):
    requests, successful, forecasts, calls = [], [], [], []
    counts = {}
    lat, lng = payload["coordinates"]

    def transport(request):
        path = request.url.path
        counts[path] = counts.get(path, 0) + 1
        requests.append({"path": path, "query": dict(request.url.params)})
        status = payload.get("status", {}).get(path, 200)
        if counts[path] <= payload.get("transientFailures", {}).get(path, 0):
            status = 503
        if status != 200:
            return httpx.Response(status, text="fixture service unavailable")
        data = {"lat": lat, "lng": lng}
        if path == "/latlng":
            if payload.get("invalidCoordinates"):
                data["lat"] = "invalid"
            return httpx.Response(200, json=data)
        if path == "/number":
            return httpx.Response(200, text=str(payload["temperature"]))
        if path == "/weather":
            return httpx.Response(200, text=payload.get("description", "Sunny"))
        raise AssertionError("Unexpected fixture HTTP endpoint")

    def model(messages, info):
        calls.append(1)
        returns = [
            p for m in messages for p in m.parts if isinstance(p, ToolReturnPart)
        ]
        if not returns:
            return ModelResponse(
                parts=[
                    ToolCallPart(
                        "get_lat_lng",
                        {"location_description": payload["city"]},
                        "location",
                    )
                ]
            )
        coordinate = returns[0].content
        if hasattr(coordinate, "model_dump"):
            coordinate = coordinate.model_dump()
        if len(returns) == 1:
            return ModelResponse(
                parts=[ToolCallPart("get_weather", coordinate, "forecast")]
            )
        weather = returns[-1].content
        return ModelResponse(
            parts=[
                TextPart(
                    f"{payload['city']}: {weather['temperature']}, {weather['description']}."
                )
            ]
        )

    output, error, messages = None, None, []
    try:
        async with httpx.AsyncClient(
            transport=httpx.MockTransport(transport)
        ) as client:
            kwargs = {"client": client}
            if "unit" in payload:
                kwargs["unit"] = payload["unit"]
            deps = app.Deps(**kwargs)
            with app.weather_agent.override(model=FunctionModel(model)):
                for _ in range(payload.get("repeat", 1)):
                    with capture_run_messages() as captured:
                        try:
                            result = await app.weather_agent.run(
                                f"Weather in {payload['city']}?", deps=deps
                            )
                            output = result.output
                        finally:
                            messages.extend(captured)
    except Exception as exception:
        output, error = None, type(exception).__name__
    # These are successful tool returns observed in the framework's messages.
    # A requested or failed call is never reported as a successful execution.
    arguments = {}
    for message in messages:
        for part in message.parts:
            if isinstance(part, ToolCallPart):
                arguments[part.tool_call_id] = part.args_as_dict()
            elif isinstance(part, ToolReturnPart):
                content = (
                    part.content.model_dump(mode="json")
                    if hasattr(part.content, "model_dump")
                    else part.content
                )
                context.tool(part.tool_name, arguments.get(part.tool_call_id), content)
                successful.append(part.tool_name)
                if part.tool_name == "get_weather":
                    forecasts.append(content)
    weather_requests = [r for r in requests if r["path"] == "/weather"]
    guard = sys.modules.get("sitecustomize")
    if guard is None or not hasattr(guard, "blocked_attempts"):
        raise RuntimeError("Offline socket guard was not loaded")
    return {
        "available": error is None and output is not None,
        "response": output,
        "errorClass": error,
        "forecasts": forecasts,
        "successfulTools": successful,
        "coordinatesForwarded": all(
            r["query"] == {"lat": str(float(lat)), "lng": str(float(lng))}
            for r in weather_requests
        ),
        "weatherRequests": len(weather_requests),
        "httpRequests": requests,
        "modelFixtureCalls": len(calls),
        "blockedNetworkAttempts": guard.blocked_attempts,
    }
