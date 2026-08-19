# LangFORM Terminologies

This file defines the shared vocabulary used by LangFORM.

## Core Concepts

### LangFORM
A framework for context, memory, retrieval, and orchestration in LLM-based and agentic AI applications.

### Context Frame
A semantically meaningful unit of information prepared for retrieval or model context. A Context Frame represents a coherent unit of meaning rather than an arbitrary fixed-size text chunk.

### Context Set
A collection of Context Frames selected for a specific model interaction.

### Context Retrieval
The process of identifying and selecting Context Frames relevant to an information need.

### Context Sufficiency
A determination of whether the current Context Set contains enough information for a Main LLM to proceed reliably.

### Context Package
A structured LangFORM output containing the user query, selected Context Frames, relevant memory, provenance, status, and optional requests.

### Orchestration
The coordination of context preparation and model interactions across LangFORM, a local SLM, a Main LLM, and the surrounding application.

## Asset Concepts

### Asset
A user-authorized information resource known to LangFORM.

### Uploaded Asset
An Asset uploaded through the surrounding application and stored in a LangFORM-managed upload location.

### Local Asset
An Asset that remains in its original location and is referenced by path.

### Web Asset
An Asset referenced through a web URL.

### Asset Reference
The location information LangFORM uses to identify or access an Asset.

### Asset Record
LangFORM's structured record describing a registered Asset.

### Asset Registry
The collection of Asset Records known to a LangFORM instance.

### Asset Metadata
Structured technical and semantic information describing an Asset.

### Technical Metadata
Information such as file name, path, reference type, file type, file size, creation date, modification date, hash, version, and availability status.

### Semantic Metadata
Information such as summary, document type, topics, keywords, entities, relationships, and related Context Frame IDs.

### Asset Relationship
A supported relationship between Assets.

### Provenance
Information identifying where content or a Context Frame originated.

## Model Concepts

### Local SLM
A Small Language Model used locally for prompt analysis, asset understanding, metadata generation, semantic organization, retrieval support, memory organization, and context preparation.

### Main LLM
A model used primarily for deeper reasoning and final response generation.

### Model Request
A structured request sent to a model.

### Model Response
A structured response returned by a model.

## Memory Concepts

### Memory
Persistent information retained by LangFORM for future interactions.

### Conversation Memory
Information derived from prior user and model interactions that may be useful later.

### Asset Memory
Persistent knowledge about registered Assets, metadata, summaries, Context Frames, and relationships.

### Framework Memory
Operational information used by LangFORM.

## Processing Concepts

### Derived Knowledge
Information created from an Asset through processing, such as extracted structure, summaries, metadata, semantic sections, and Context Frames.

### Generated Artifact
A new file intentionally created during an application workflow.

### Capability
A task that can be performed by LangFORM or by the surrounding platform.

### Tool
A callable implementation that performs a capability.

### Adapter
A component that translates between LangFORM's internal interface and an external model, runtime, service, or platform.

### Registry
A structured collection of records describing resources or capabilities.

### Session
A logical interaction context grouping related user requests, responses, memory, and state.

## Orchestration Concepts

### Action Request
A structured indication that another action is required before a workflow can continue.

### External Action
An action performed by the surrounding platform or agent runtime instead of LangFORM core.

### Context Request
A request for additional information or Context Frames.

### Iteration
One cycle of context preparation, model interaction, evaluation, and possible context expansion.

## Status Terms

### context_ready
Relevant context has been prepared.

### more_context_required
Additional Context Frames or memory are needed.

### external_action_required
The surrounding application needs to perform an action.

### final
No additional LangFORM context operation is required.

### error
LangFORM cannot continue until an error is resolved.
