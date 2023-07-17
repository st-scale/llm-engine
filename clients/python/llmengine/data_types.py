"""
DTOs for LLM APIs.
"""
import datetime
from enum import Enum
from typing import Any, Dict, List, Literal, Optional, Union

from pydantic import BaseModel, Field, HttpUrl

CpuSpecificationType = Union[str, int, float]
StorageSpecificationType = Union[str, int, float]  # TODO(phil): we can make this more specific.


class LLMInferenceFramework(str, Enum):
    DEEPSPEED = "deepspeed"


class LLMSource(str, Enum):
    HUGGING_FACE = "hugging_face"


class GpuType(str, Enum):
    """Lists allowed GPU types for LLMEngine."""

    NVIDIA_TESLA_T4 = "nvidia-tesla-t4"
    NVIDIA_AMPERE_A10 = "nvidia-ampere-a10"
    NVIDIA_AMPERE_A100 = "nvidia-a100"


class ModelEndpointType(str, Enum):
    ASYNC = "async"
    SYNC = "sync"
    STREAMING = "streaming"


class ModelEndpointStatus(str, Enum):
    # Duplicates common/types::EndpointStatus, when refactor is done, delete the old type
    # See EndpointStatus for status explanations
    READY = "READY"
    UPDATE_PENDING = "UPDATE_PENDING"
    UPDATE_IN_PROGRESS = "UPDATE_IN_PROGRESS"
    UPDATE_FAILED = "UPDATE_FAILED"
    DELETE_IN_PROGRESS = "DELETE_IN_PROGRESS"


class CallbackBasicAuth(BaseModel):
    kind: Literal["basic"]
    username: str
    password: str


class CallbackmTLSAuth(BaseModel):
    kind: Literal["mtls"]
    cert: str
    key: str


class CallbackAuth(BaseModel):
    __root__: Union[CallbackBasicAuth, CallbackmTLSAuth] = Field(..., discriminator="kind")


class ModelEndpointDeploymentState(BaseModel):
    """
    This is the entity-layer class for the deployment settings related to a Model Endpoint.
    """

    min_workers: int = Field(..., ge=0)
    max_workers: int = Field(..., ge=0)
    per_worker: int = Field(..., gt=0)
    available_workers: Optional[int] = Field(default=None, ge=0)
    unavailable_workers: Optional[int] = Field(default=None, ge=0)


class ModelEndpointResourceState(BaseModel):
    """
    This is the entity-layer class for the resource settings per worker of a Model Endpoint.
    """

    cpus: CpuSpecificationType  # TODO(phil): try to use decimal.Decimal
    gpus: int = Field(..., ge=0)
    memory: StorageSpecificationType
    gpu_type: Optional[GpuType]
    storage: Optional[StorageSpecificationType]
    optimize_costs: Optional[bool]


class GetModelEndpointV1Response(BaseModel):
    id: str
    name: str
    endpoint_type: ModelEndpointType
    destination: str
    deployment_name: Optional[str] = Field(default=None)
    metadata: Optional[Dict[str, Any]] = Field(default=None)  # TODO: JSON type
    bundle_name: str
    status: ModelEndpointStatus
    post_inference_hooks: Optional[List[str]] = Field(default=None)
    default_callback_url: Optional[HttpUrl] = Field(default=None)
    default_callback_auth: Optional[CallbackAuth] = Field(default=None)
    labels: Optional[Dict[str, str]] = Field(default=None)
    aws_role: Optional[str] = Field(default=None)
    results_s3_bucket: Optional[str] = Field(default=None)
    created_by: str
    created_at: datetime.datetime
    last_updated_at: datetime.datetime
    deployment_state: Optional[ModelEndpointDeploymentState] = Field(default=None)
    resource_state: Optional[ModelEndpointResourceState] = Field(default=None)
    num_queued_items: Optional[int] = Field(default=None)
    public_inference: Optional[bool] = Field(default=None)


class TaskStatus(str, Enum):
    """
    Specifies the status of a request as an enumeration.

    Valid values are one of PENDING, STARTED, SUCCESS, FAILURE, and UNDEFINED
    """

    PENDING = "PENDING"
    STARTED = "STARTED"
    SUCCESS = "SUCCESS"
    FAILURE = "FAILURE"
    UNDEFINED = "UNDEFINED"


class CreateLLMModelEndpointV1Request(BaseModel):
    name: str

    # LLM specific fields
    model_name: str
    source: LLMSource = LLMSource.HUGGING_FACE
    inference_framework: LLMInferenceFramework = LLMInferenceFramework.DEEPSPEED
    inference_framework_image_tag: str
    num_shards: int
    """
    Number of shards to distribute the model onto GPUs.
    """

    # General endpoint fields
    metadata: Dict[str, Any]  # TODO: JSON type
    post_inference_hooks: Optional[List[str]]
    endpoint_type: ModelEndpointType = ModelEndpointType.SYNC
    cpus: CpuSpecificationType
    gpus: int
    memory: StorageSpecificationType
    gpu_type: GpuType
    storage: Optional[StorageSpecificationType]
    optimize_costs: Optional[bool]
    min_workers: int
    max_workers: int
    per_worker: int
    labels: Dict[str, str]
    prewarm: Optional[bool]
    high_priority: Optional[bool]
    default_callback_url: Optional[HttpUrl]
    default_callback_auth: Optional[CallbackAuth]
    public_inference: Optional[bool] = True  # LLM endpoints are public by default.


class CreateLLMModelEndpointV1Response(BaseModel):
    endpoint_creation_task_id: str


class GetLLMModelEndpointV1Response(BaseModel):
    id: str
    """
    The autogenerated ID of the LLMEngine endpoint.
    """

    name: str
    model_name: str
    source: LLMSource
    inference_framework: LLMInferenceFramework
    inference_framework_image_tag: str
    num_shards: int
    spec: GetModelEndpointV1Response


class ListLLMModelEndpointsV1Response(BaseModel):
    model_endpoints: List[GetLLMModelEndpointV1Response]


# Delete and update use the default LLMEngine endpoint APIs.


class CompletionSyncV1Request(BaseModel):
    """
    Request object for a synchronous prompt completion task.
    """

    prompts: List[str] = Field(..., min_items=1)
    max_new_tokens: int = Field(..., gt=0)
    temperature: float = Field(..., gt=0.0)


class CompletionOutput(BaseModel):
    """
    Represents the output of a completion request to a model.
    """

    text: str
    """The text of the completion."""

    num_prompt_tokens: Optional[int]
    """Number of tokens in the prompt."""

    num_completion_tokens: int
    """Number of tokens in the completion."""


class CompletionSyncV1Response(BaseModel):
    """
    Response object for a synchronous prompt completion.
    """

    status: TaskStatus
    """Task status."""

    outputs: List[CompletionOutput]
    """List of completion outputs."""

    traceback: Optional[str] = None
    """Traceback if the task failed."""


class CompletionStreamV1Request(BaseModel):
    """
    Request object for a streaming prompt completion.
    """

    prompt: str = Field(..., min_length=1)
    max_new_tokens: int = Field(..., gt=0)
    temperature: float = Field(..., gt=0.0)


class CompletionStreamOutput(BaseModel):
    text: str
    """The text of the completion."""

    finished: bool
    """Whether the completion is finished."""

    num_prompt_tokens: Optional[int] = None
    """Number of tokens in the prompt."""

    num_completion_tokens: Optional[int] = None
    """Number of tokens in the completion."""


class CompletionStreamV1Response(BaseModel):
    """
    Response object for a stream prompt completion task.
    """

    status: TaskStatus
    """Task status."""

    output: Optional[CompletionStreamOutput] = None
    """Completion output."""

    traceback: Optional[str] = None
    """Traceback if the task failed."""


# everything below copied from scaleapi/packages/spellbook-backend/server/spellbook_server/dtos.py


class CreateFineTuneRequest(BaseModel):
    model: str = Field(..., description="Identifier of base model to train from.")
    training_file: str = Field(..., description="Path to file of training dataset. Dataset must be a csv with columns 'prompt' and 'response'.")
    validation_file: Optional[str] = Field(default=None, description="Path to file of validation dataset. Has the same format as training_file. If not provided, we will generate a split from the training dataset.")
    hyperparameters: Optional[Dict[str, Any]] = Field(default=None, description="Hyperparameters to pass in to training job.")
    suffix: Optional[str] = Field(default=None, description="Optional user-provided identifier suffix for the fine-tuned model.")


class CreateFineTuneResponse(BaseModel):
    """
    Response object for creating a FineTune.
    """

    fine_tune_id: str = Field(..., description="ID of the created fine-tuning job.")
    """
    The ID of the FineTune.
    """


class BatchJobStatus(str, Enum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    SUCCESS = "SUCCESS"
    FAILURE = "FAILURE"
    CANCELLED = "CANCELLED"
    UNDEFINED = "UNDEFINED"
    TIMEOUT = "TIMEOUT"


class GetFineTuneResponse(BaseModel):
    """
    Response object for retrieving a FineTune.
    """

    fine_tune_id: str = Field(..., description="ID of the requested job.")
    """
    The ID of the FineTune.
    """

    status: BatchJobStatus = Field(..., description="Status of the requested job.")
    """
    The status of the FineTune job.
    """


class ListFineTunesResponse(BaseModel):
    """
    Response object for listing FineTunes.
    """

    jobs: List[GetFineTuneResponse] = Field(..., description="List of fine-tuning jobs and their statuses.")
    """
    A list of FineTunes, represented as `GetFineTuneResponse`s.
    """


class CancelFineTuneResponse(BaseModel):
    """
    Response object for cancelling a FineTune.
    """

    success: bool = Field(..., description="Whether cancellation was successful.")
    """
    Whether the cancellation succeeded.
    """
