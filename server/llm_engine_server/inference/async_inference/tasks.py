import os
from typing import Any, Callable, Dict, Optional

from celery import Task
from celery.signals import worker_process_init
from llm_engine_server.common.constants import READYZ_FPATH
from llm_engine_server.common.dtos.tasks import EndpointPredictV1Request
from llm_engine_server.common.serialization_utils import str_to_bool
from llm_engine_server.core.loggers import make_logger
from llm_engine_server.core.utils.timer import timer
from llm_engine_server.domain.entities import ModelEndpointConfig
from llm_engine_server.inference.async_inference.celery import async_inference_service
from llm_engine_server.inference.common import (
    get_endpoint_config,
    load_predict_fn_or_cls,
    run_predict,
)
from llm_engine_server.inference.infra.gateways.datadog_inference_monitoring_metrics_gateway import (
    DatadogInferenceMonitoringMetricsGateway,
)
from llm_engine_server.inference.post_inference_hooks import PostInferenceHooksHandler

logger = make_logger(__name__)

# This should be safe as long as the celery workers are separate processes
#    (or we're using pool=solo) so they're not shared between threads
predict_fn_or_cls: Optional[Callable] = None
endpoint_config: Optional[ModelEndpointConfig] = None
hooks: Optional[PostInferenceHooksHandler] = None


def init_worker_global():
    global predict_fn_or_cls, endpoint_config, hooks

    with timer(logger=logger, name="load_predict_fn_or_cls"):
        predict_fn_or_cls = load_predict_fn_or_cls()

    endpoint_config = get_endpoint_config()
    hooks = PostInferenceHooksHandler(
        endpoint_name=endpoint_config.endpoint_name,
        bundle_name=endpoint_config.bundle_name,
        post_inference_hooks=endpoint_config.post_inference_hooks,
        user_id=endpoint_config.user_id,
        default_callback_url=endpoint_config.default_callback_url,
        default_callback_auth=endpoint_config.default_callback_auth,
        monitoring_metrics_gateway=DatadogInferenceMonitoringMetricsGateway(),
    )
    # k8s health check
    with open(READYZ_FPATH, "w") as f:
        f.write("READY")


@worker_process_init.connect
def init_worker_hook(*args, **kwargs):
    # Note: the PREWARM variable is stored as a string taking on values "true" or "false".
    # Enforced on endpoint creation
    if str_to_bool(os.getenv("PREWARM")):
        init_worker_global()
        logger.info(f"Initialized worker on {os.getpid()}")
    else:
        logger.info(f"Not prewarming for {os.getpid()}")


# pod is default ready if we're not prewarming
if not str_to_bool(os.getenv("PREWARM")):
    with open(READYZ_FPATH, "w") as f:
        f.write("READY")


class InferenceTask(Task):
    def __init__(self):
        self.worker_initialized = False

    def init_worker(self):
        if not predict_fn_or_cls or not hooks:
            # This code runs when the task is run, at which point we should have finished
            #   init_worker_hook or are not executing it, so we shouldn't be double initializing
            init_worker_global()
            logger.info(f"Late initialized worker on {os.getpid()}")
        self.worker_initialized = True

    def predict(self, request_params, return_pickled):
        if not self.worker_initialized:
            self.init_worker()
        request_params["return_pickled"] = return_pickled
        request_params_pydantic = EndpointPredictV1Request.parse_obj(request_params)
        return run_predict(predict_fn_or_cls, request_params_pydantic)  # type: ignore

    def on_success(self, retval, task_id, args, kwargs):
        request_params = args[0]
        request_params_pydantic = EndpointPredictV1Request.parse_obj(request_params)
        hooks.handle(request_params_pydantic, retval, task_id)  # type: ignore


@async_inference_service.task(base=InferenceTask)
def predict(request_params: Dict[str, Any], return_pickled=True):
    return predict.predict(request_params, return_pickled)
