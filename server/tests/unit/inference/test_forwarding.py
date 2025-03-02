import json
from dataclasses import dataclass
from typing import Mapping
from unittest import mock

import pytest
from llm_engine_server.core.utils.env import environment
from llm_engine_server.domain.entities import ModelEndpointConfig
from llm_engine_server.inference.forwarding.forwarding import (
    ENV_SERIALIZE_RESULTS_AS_STRING,
    KEY_SERIALIZE_RESULTS_AS_STRING,
    Forwarder,
    LoadForwarder,
    LoadStreamingForwarder,
    StreamingForwarder,
)
from llm_engine_server.inference.infra.gateways.datadog_inference_monitoring_metrics_gateway import (
    DatadogInferenceMonitoringMetricsGateway,
)
from llm_engine_server.inference.post_inference_hooks import PostInferenceHooksHandler

PAYLOAD: Mapping[str, Mapping[str, str]] = {"hello": "world"}


def mocked_get(*args, **kwargs):  # noqa
    @dataclass
    class mocked_static_status_code:
        status_code: int = 200

    return mocked_static_status_code()


def mocked_post(*args, **kwargs):  # noqa
    @dataclass
    class mocked_static_json:
        def json(self) -> dict:
            return PAYLOAD  # type: ignore

    return mocked_static_json()


def mocked_sse_client(*args, **kwargs):  # noqa
    @dataclass
    class Event:
        data: str

    @dataclass
    class mocked_static_events:
        def events(self) -> list:
            payload_json = json.dumps(PAYLOAD)
            return [Event(data=payload_json), Event(data=payload_json)]

    return mocked_static_events()


def mocked_get_endpoint_config():
    return ModelEndpointConfig(
        endpoint_name="test_endpoint_name",
        bundle_name="test_bundle_name",
    )


@pytest.fixture
def post_inference_hooks_handler():
    handler = PostInferenceHooksHandler(
        endpoint_name="test_endpoint_name",
        bundle_name="test_bundle_name",
        post_inference_hooks=[],
        user_id="test_user_id",
        default_callback_url=None,
        default_callback_auth=None,
        monitoring_metrics_gateway=DatadogInferenceMonitoringMetricsGateway(),
    )
    return handler


@mock.patch("requests.post", mocked_post)
@mock.patch("requests.get", mocked_get)
def test_forwarders(post_inference_hooks_handler):
    fwd = Forwarder(
        "ignored",
        llm_engine_unwrap=True,
        serialize_results_as_string=False,
        post_inference_hooks_handler=post_inference_hooks_handler,
        wrap_response=True,
    )
    json_response = fwd({"args": {"ignore": "me"}})
    _check(json_response)


def _check(json_response) -> None:
    assert json_response == {"result": PAYLOAD}


def _check_responses_not_wrapped(json_response) -> None:
    assert json_response == PAYLOAD


def _check_streaming(streaming_response) -> None:
    streaming_response_list = list(streaming_response)
    assert len(streaming_response_list) == 2
    assert streaming_response_list[0] == {"result": PAYLOAD}
    assert streaming_response_list[1] == {"result": PAYLOAD}


def _check_streaming_serialized(streaming_response) -> None:
    streaming_response_list = list(streaming_response)
    assert len(streaming_response_list) == 2
    assert streaming_response_list[0] == {"result": json.dumps(PAYLOAD)}
    assert streaming_response_list[1] == {"result": json.dumps(PAYLOAD)}


@mock.patch("requests.post", mocked_post)
@mock.patch("requests.get", mocked_get)
def test_forwarders_serialize_results_as_string(post_inference_hooks_handler):
    fwd = Forwarder(
        "ignored",
        llm_engine_unwrap=True,
        serialize_results_as_string=True,
        post_inference_hooks_handler=post_inference_hooks_handler,
        wrap_response=True,
    )
    json_response = fwd({"args": {"ignore": "me"}})
    _check_serialized(json_response)


def _check_serialized(json_response) -> None:
    assert isinstance(json_response["result"], str)
    assert len(json_response) == 1, f"expecting only 'result' key, but got {json_response=}"
    assert json.loads(json_response["result"]) == PAYLOAD


@mock.patch("requests.post", mocked_post)
@mock.patch("requests.get", mocked_get)
def test_forwarders_override_serialize_results(post_inference_hooks_handler):
    fwd = Forwarder(
        "ignored",
        llm_engine_unwrap=True,
        serialize_results_as_string=True,
        post_inference_hooks_handler=post_inference_hooks_handler,
        wrap_response=True,
    )
    json_response = fwd({"args": {"ignore": "me", KEY_SERIALIZE_RESULTS_AS_STRING: False}})
    _check(json_response)
    assert json_response == {"result": PAYLOAD}

    fwd = Forwarder(
        "ignored",
        llm_engine_unwrap=True,
        serialize_results_as_string=False,
        post_inference_hooks_handler=post_inference_hooks_handler,
        wrap_response=True,
    )
    json_response = fwd({"args": {"ignore": "me", KEY_SERIALIZE_RESULTS_AS_STRING: True}})
    _check_serialized(json_response)


@mock.patch("requests.post", mocked_post)
@mock.patch("requests.get", mocked_get)
def test_forwarder_does_not_wrap_response(post_inference_hooks_handler):
    fwd = Forwarder(
        "ignored",
        llm_engine_unwrap=True,
        serialize_results_as_string=False,
        post_inference_hooks_handler=post_inference_hooks_handler,
        wrap_response=False,
    )
    json_response = fwd({"args": {"ignore": "me"}})
    _check_responses_not_wrapped(json_response)


@mock.patch("requests.post", mocked_post)
@mock.patch("requests.get", mocked_get)
@mock.patch(
    "llm_engine_server.inference.forwarding.forwarding.get_endpoint_config",
    mocked_get_endpoint_config,
)
def test_forwarder_loader():
    fwd = LoadForwarder(serialize_results_as_string=True).load(None, None)  # type: ignore
    json_response = fwd({"args": {"ignore": "me"}})
    _check_serialized(json_response)

    fwd = LoadForwarder(serialize_results_as_string=False).load(None, None)  # type: ignore
    json_response = fwd({"args": {"ignore": "me"}})
    _check(json_response)

    fwd = LoadForwarder(wrap_response=False).load(None, None)  # type: ignore
    json_response = fwd({"args": {"ignore": "me"}})
    _check_responses_not_wrapped(json_response)


@mock.patch("requests.post", mocked_post)
@mock.patch("requests.get", mocked_get)
@mock.patch(
    "llm_engine_server.inference.forwarding.forwarding.get_endpoint_config",
    mocked_get_endpoint_config,
)
def test_forwarder_loader_env_serialize_behavior(post_inference_hooks_handler):
    with environment(**{ENV_SERIALIZE_RESULTS_AS_STRING: "false"}):
        fwd = LoadForwarder(serialize_results_as_string=True).load(None, None)  # type: ignore
    json_response = fwd({"args": {"ignore": "me"}})
    _check(json_response)

    with environment(**{ENV_SERIALIZE_RESULTS_AS_STRING: "true"}):
        fwd = LoadForwarder(serialize_results_as_string=False).load(None, None)  # type: ignore
    json_response = fwd({"args": {"ignore": "me"}})
    _check_serialized(json_response)


@mock.patch("requests.post", mocked_post)
@mock.patch("requests.get", mocked_get)
def test_forwarder_serialize_within_args(post_inference_hooks_handler):
    # standard Spellbook-Serve-created forwarder
    fwd = Forwarder(
        "ignored",
        llm_engine_unwrap=True,
        serialize_results_as_string=True,
        post_inference_hooks_handler=post_inference_hooks_handler,
        wrap_response=True,
    )
    # expected: no `serialize_results_as_string` at top-level nor in 'args'
    json_response = fwd({"something": "to ignore", "args": {"my": "payload", "is": "here"}})
    _check_serialized(json_response)
    # unwraps under "args" to find `serialize_results_as_string`
    payload = {
        "something": "to ignore",
        "args": {"my": "payload", "is": "here", "serialize_results_as_string": False},
    }
    json_response = fwd(payload)
    _check(json_response)
    # w/o unwrapping it won't "find" the `"serialize_results_as_string": False` directive
    fwd = Forwarder(
        "ignored",
        llm_engine_unwrap=False,
        serialize_results_as_string=True,
        post_inference_hooks_handler=post_inference_hooks_handler,
        wrap_response=True,
    )
    json_response = fwd(payload)
    _check_serialized(json_response)


@mock.patch("requests.post", mocked_post)
@mock.patch("requests.get", mocked_get)
@mock.patch("sseclient.SSEClient", mocked_sse_client)
def test_streaming_forwarders(post_inference_hooks_handler):
    fwd = StreamingForwarder(
        "ignored",
        llm_engine_unwrap=True,
        serialize_results_as_string=False,
        post_inference_hooks_handler=post_inference_hooks_handler,
    )
    response = fwd({"args": {"ignore": "me"}})
    _check_streaming(response)


@mock.patch("requests.post", mocked_post)
@mock.patch("requests.get", mocked_get)
@mock.patch("sseclient.SSEClient", mocked_sse_client)
@mock.patch(
    "llm_engine_server.inference.forwarding.forwarding.get_endpoint_config",
    mocked_get_endpoint_config,
)
def test_streaming_forwarder_loader():
    fwd = LoadStreamingForwarder(serialize_results_as_string=True).load(None, None)  # type: ignore
    json_response = fwd({"args": {"ignore": "me"}})
    _check_streaming_serialized(json_response)

    fwd = LoadStreamingForwarder(serialize_results_as_string=False).load(None, None)  # type: ignore
    response = fwd({"args": {"ignore": "me"}})
    _check_streaming(response)
