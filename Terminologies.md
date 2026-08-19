# LangFORM Terminologies

This file defines the shared vocabulary used by LangFORM.

The definitions are intended to be understandable by the LangFORM core, the local SLM, Main LLMs, platform applications, external agents, adapters, tools, and contributors.

This file is expected to grow as LangFORM develops.

## Core Concepts

### LangFORM
A framework for context, memory, retrieval, and orchestration in LLM-based and agentic AI applications.

### Context Frame
A semantically meaningful unit of information prepared for retrieval or model context. A Context Frame should represent a coherent unit of meaning rather than an arbitrary fixed-size text chunk.

### Context Set
A collection of Context Frames selected for a specific model interaction.

### Context Retrieval
The process of identifying and selecting Context Frames relevant to the current information need.

### Context Sufficiency
A determination of whether the currently supplied Context Set contains enough information for the Main LLM to proceed reliably.

### Orchestration
The coordination of context preparation and model interactions across LangFORM, the local SLM, the Main LLM, and the surrounding application.

## Asset Concepts

### Asset
A user-authorized information resource known to LangFORM.

### Uploaded Asset
An Asset uploaded through the surrounding application and stored in a LangFORM-managed upload location.

### Local Asset
An Asset that remains in its original location on the user's local system and is referenced by path.

### Web Asset
An Asset referenced through a web URL.

### Asset Reference
The location information LangFORM uses to identify or access an Asset, such as a local path or web URL.

### Asset Record
LangFORM's structured record describing a registered Asset.

### Asset Registry
The collection of Asset Records known to a LangFORM instance.

### Asset Metadata
Structured technical and semantic information describing an Asset.

### Technical Metadata
Information such as file name, path, reference type, file type, file size, creation date, modification date, hash, version, and availability status.

### Semantic Metadata
Information such as content summary, document type, topics, keywords, entities, relationships, and related Context Frame IDs.

### Asset Relationship
A supported relationship between two or more Assets, such as related topic, source dependency, version relationship, or another meaningful connection.

### Provenance
Information identifying where content or a Context Frame originated.

## Model Concepts

### Local SLM
The local Small Language Model used by LangFORM for prompt analysis, asset understanding, metadata generation, semantic organization, retrieval support, memory organization, and context preparation.

### Main LLM
The model used primarily for deeper reasoning and final response generation.

### Model Request
A structured request sent to a model.

### Model Response
A structured response returned by a model.

## Memory Concepts

### Memory
Persistent information retained by LangFORM for future interactions.

### Conversation Memory
Information derived from prior user and model interactions that may be useful in later turns.

### Asset Memory
Persistent knowledge about registered Assets, their metadata, summaries, Context Frames, and relationships.

### Framework Memory
Operational information used by LangFORM, such as configuration, registered capabilities, workflow state, and internal references.

## Processing Concepts

### Derived Knowledge
Information created from an Asset through processing, such as extracted structure, summaries, metadata, semantic sections, and Context Frames.

### Generated Artifact
A new file intentionally created during an application workflow, such as a report, draft, code file, export, or analysis result.

### Capability
A task that can be performed by LangFORM or by the surrounding platform through an available implementation.

### Tool
A callable implementation that performs a capability.

### Adapter
A component that translates between LangFORM's internal interface and an external model, runtime, service, or platform.

### Registry
A structured collection of records describing resources, capabilities, or other known LangFORM objects.

### Session
A logical interaction context that groups related user requests, responses, memory, and state.

## Orchestration Concepts

### Action Request
A structured indication that an additional action is required before the workflow can continue.

### External Action
An action that must be performed by the surrounding platform or agent runtime rather than by LangFORM itself.

### Context Request
A request for additional information or Context Frames.

### Iteration
One cycle of context preparation, model interaction, evaluation, and possible context expansion.

### Context Package
A structured LangFORM output containing the user's request, selected Context Frames, relevant memory, provenance, status, and other information needed by a receiving model or application.

## Initial Status Terms

### context_ready
LangFORM has prepared a Context Package that is ready for use.

### more_context_required
The current Context Set is insufficient and additional retrieval is required.

### external_action_required
The workflow requires an action that should be performed by the surrounding application or agent runtime.

### final
The workflow has reached a state where no additional LangFORM context operation is required.

### error
LangFORM cannot continue the requested operation without resolving an error.
