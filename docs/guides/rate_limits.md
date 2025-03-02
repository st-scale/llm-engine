# Overview

## What are rate limits?
A rate limit is a restriction that an API imposes on the number of times a user or client can access the server within 
a specified period of time.

## Why do we have rate limits?
Rate limits are a common practice for APIs, and they're put in place for a few different reasons:

* **They help protect against abuse or misuse of the API.** For example, a malicious actor could flood the API with 
requests in an attempt to overload it or cause disruptions in the service. By setting rate limits, the LLM Engine 
server can prevent this kind of activity.
* **Rate limits help ensure that everyone has fair access to API.** If one person or organization makes an excessive 
number of requests, it could bog down the API for everyone else. By throttling the number of requests that a single 
user can make, LLM Engine ensures that the most number of people have an opportunity to use the API without 
experiencing slowdowns. This also applies when self-hosting LLM Engine, as all internal users within an organization 
would have fair access.
* **Rate limits can help manage the aggregate load on the server infrastructure.** If requests to the API increase 
dramatically, it could tax the servers and cause performance issues. By setting rate limits, LLM Engine can help 
maintain a smooth and consistent experience for all users. This is especially important when self-hosting LLM Engine.

## How do I know if I am rate limited?
Per standard HTTP practices, your request will receive a response with HTTP status code of `429`, `Too Many Requests`.


## What are the rate limits for our API?
The LLM Engine API is currently in a preview mode, and therefore we currently do not have any advertised rate limits.
As the API moves towards a production release, we will update this section with specific rate limits. For now, the API
will return HTTP 429 on an as-needed basis.

# Error mitigation
## Retrying with exponential backoff
One easy way to avoid rate limit errors is to automatically retry requests with a random exponential backoff. 
Retrying with exponential backoff means performing a short sleep when a rate limit error is hit, then retrying the 
unsuccessful request. If the request is still unsuccessful, the sleep length is increased and the process is repeated. 
This continues until the request is successful or until a maximum number of retries is reached. This approach has many benefits:

* Automatic retries means you can recover from rate limit errors without crashes or missing data
* Exponential backoff means that your first retries can be tried quickly, while still benefiting from longer delays if your first few retries fail
* Adding random jitter to the delay helps retries from all hitting at the same time.

Below are a few example solutions **for Python** that use exponential backoff.

### Example #1: Using the `tenacity` library

Tenacity is an Apache 2.0 licensed general-purpose retrying library, written in Python, to simplify the task of adding 
retry behavior to just about anything. To add exponential backoff to your requests, you can use the tenacity.retry 
decorator. The below example uses the tenacity.wait_random_exponential function to add random exponential backoff to a 
request.

```python
import llmengine
from tenacity import (
    retry,
    stop_after_attempt,
    wait_random_exponential,
)  # for exponential backoff

@retry(wait=wait_random_exponential(min=1, max=60), stop=stop_after_attempt(6))
def completion_with_backoff(**kwargs):
    return llmengine.Completion.create(**kwargs)

completion_with_backoff(model_name="llama-7b", prompt="Why is the sky blue?")
```

### Example #2: Using the `backoff` library
Another python library that provides function decorators for backoff and retry is backoff:

```python
import llmengine
import backoff
@backoff.on_exception(backoff.expo, llmengine.error.RateLimitError)
def completions_with_backoff(**kwargs):
    return llmengine.Completion.create(**kwargs)

completions_with_backoff(model_name="llama-7b", prompt="Why is the sky blue?")
```
