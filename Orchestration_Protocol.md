# LangFORM Orchestration Protocol

## Purpose

This protocol defines how LangFORM structures context-related communication between the local SLM, the Main LLM, and the surrounding platform application.

LangFORM does not require the surrounding application to use a specific UI, model provider, tool provider, or agent framework.

The application decides how to use LangFORM outputs.

## Core Principle

LangFORM prepares context and communicates requirements through structured outputs.

The surrounding application remains responsible for executing general external actions such as web search, code execution, browser operations, email actions, and external API calls.

## Basic Flow

1. The application sends a user request and available resource references to LangFORM.
2. The local SLM analyzes the request.
3. LangFORM retrieves or creates relevant Context Frames.
4. LangFORM prepares a Context Package.
5. The Context Package is provided to the Main LLM or returned to the application, depending on the integration.
6. The Main LLM may determine that the context is sufficient, more context is needed, or an External Action is needed.
7. LangFORM performs additional context retrieval when appropriate.
8. External Action requests are returned to the surrounding application.
9. The application may return action results to LangFORM.
10. LangFORM may convert useful results into Context Frames and continue the context cycle.

## LangFORM Input

A LangFORM request may contain:

```json
{
  "session_id": "session_001",
  "user_query": "Compare the findings in these reports.",
  "asset_references": ["asset_001", "asset_002"],
  "external_results": []
}
```

## Context Package

A standard Context Package may contain:

```json
{
  "status": "context_ready",
  "session_id": "session_001",
  "user_query": "Compare the findings in these reports.",
  "context_frames": [
    {
      "frame_id": "frame_001",
      "asset_id": "asset_001",
      "content": "...",
      "summary": "...",
      "provenance": {
        "source": "...",
        "location": "..."
      }
    }
  ],
  "memory": [],
  "request": null
}
```

## Status Values

### context_ready
Relevant context has been prepared and is ready for the next model or application step.

### more_context_required
Additional Context Frames or memory are needed.

### external_action_required
The workflow requires the surrounding application to perform an action.

### final
No additional LangFORM context operation is required.

### error
LangFORM cannot continue until an error is resolved.

## Requesting More Context

Example:

```json
{
  "status": "more_context_required",
  "request": {
    "type": "retrieve_context",
    "information_need": "Find the methodology used to select participants.",
    "asset_scope": ["asset_001"]
  }
}
```

## Requesting an External Action

Example:

```json
{
  "status": "external_action_required",
  "request": {
    "action_id": "action_001",
    "type": "web_search",
    "description": "Find the latest published market price.",
    "input": {
      "query": "..."
    }
  }
}
```

LangFORM does not define how the application must perform the action.

The application may use any compatible tool, provider, runtime, or implementation.

## Returning an External Action Result

The surrounding application may return:

```json
{
  "action_id": "action_001",
  "status": "completed",
  "result": "..."
}
```

LangFORM may analyze the result and create one or more Context Frames when the result is useful for subsequent reasoning.

## Model Independence

LangFORM should not require a specific Main LLM provider.

The Context Package should be usable by adapters for different models.

The local SLM should also be accessed through a model adapter rather than hard-coded to one runtime.

## Platform Independence

LangFORM does not control:
- application UI
- authentication
- user account management
- web search implementation
- code execution implementation
- external API implementation
- browser automation
- email operations
- final display of results

LangFORM communicates through its defined input and output structures.

## Protocol Evolution

This protocol is an initial specification for v0.0.1.

Field names, statuses, schemas, and message types may evolve as the framework is implemented and tested.
