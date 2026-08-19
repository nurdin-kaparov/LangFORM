# LangFORM Orchestration Protocol

## Purpose

This protocol defines LangFORM's structured communication principles with local SLMs, Main LLMs, and surrounding applications.

LangFORM does not require a specific UI, LLM provider, tool provider, or agent framework.

## Basic Flow

1. The application supplies a user request and optional Asset references.
2. LangFORM analyzes or processes required Assets.
3. LangFORM retrieves or creates relevant Context Frames.
4. LangFORM builds a Context Package.
5. The package is provided to the next model or returned to the application.
6. More context may be requested if needed.
7. External actions are requested from the surrounding application.
8. External results can be returned to LangFORM and converted into Context Frames.

## Context Package

Example:

```json
{
  "status": "context_ready",
  "session_id": "session_001",
  "user_query": "Compare the findings.",
  "context_frames": [],
  "memory": [],
  "request": null
}
```

## Status Values

- `context_ready`
- `more_context_required`
- `external_action_required`
- `final`
- `error`

## External Action Request

Example:

```json
{
  "status": "external_action_required",
  "request": {
    "action_id": "action_001",
    "type": "web_search",
    "description": "Find current market data.",
    "input": {
      "query": "..."
    }
  }
}
```

LangFORM does not prescribe how the platform performs the requested action.

## External Action Result

Example:

```json
{
  "action_id": "action_001",
  "status": "completed",
  "result": "..."
}
```

LangFORM may convert useful results into Context Frames.

## Model Independence

Model adapters should isolate provider-specific request and response formats from LangFORM core.

## Platform Independence

LangFORM does not control the application's UI, authentication, web-search implementation, code runner, browser automation, email system, external APIs, or final display.
