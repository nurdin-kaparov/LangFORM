# LangFORM

**Version:** v0.0.1-2026.08.18

LangFORM is a context, memory, retrieval, and orchestration framework for LLM-based and agentic AI applications.

LangFORM is designed to sit between an application and the models it uses. The application remains responsible for its own UI, agent runtime, external tools, and business logic. LangFORM focuses on preparing and managing the information that models need.

## Core Purpose

LangFORM helps an application provide the right context to a model instead of blindly sending entire files, long conversation histories, or unrelated information.

The framework uses a local Small Language Model (SLM) to help analyze user requests, understand registered assets, organize information, create Context Frames, retrieve relevant information, and support context orchestration.

A Main LLM can then receive the user's request together with selected Context Frames and relevant memory.

If the supplied context is not sufficient, additional context can be requested and retrieved before the final response is produced.

## Context Frames

A Context Frame is a semantically meaningful unit of information.

A Context Frame is not simply a fixed-size text chunk. It should represent a coherent piece of meaning such as a section, concept, result, definition, argument, procedure, or other useful information unit.

Context Frames retain provenance so LangFORM can identify where the information came from.

## Assets

An Asset is a user-authorized information resource.

In v0.0.1, an Asset may be:
- a file uploaded through the application
- a local file referenced by its path
- a file available through a web URL

A local file remains in its original location. LangFORM stores a reference to it rather than moving it.

A file uploaded through an application may be stored in LangFORM's managed `uploaded_assets` area.

LangFORM maintains an Asset Record for each registered Asset.

## Asset Metadata

Asset Metadata can contain technical and semantic information.

Technical metadata may include:
- Asset ID
- file name
- location
- reference type
- file type
- file size
- creation date
- modification date
- hash or version information
- availability status

Semantic metadata may include:
- content summary
- document type
- topics
- keywords
- important entities
- relationships to other Assets
- related Context Frame IDs

## Local SLM

The local SLM supports LangFORM's context-management work.

Its responsibilities can include:
- analyzing the user's request
- deciding what information is needed
- analyzing Assets
- creating summaries
- creating or updating metadata
- identifying semantic sections
- creating Context Frames
- retrieving relevant Context Frames
- organizing conversation memory
- helping determine whether more context is required

The local SLM is not normally the final user-facing reasoning model when a Main LLM is available.

## Main LLM

The Main LLM is typically responsible for deeper reasoning and final response generation.

LangFORM provides the Main LLM with structured context prepared from relevant Context Frames, memory, and the user's current request.

The Main LLM may indicate that the current context is sufficient or that additional information is needed.

## Platform Independence

LangFORM does not control the developer's user interface.

The surrounding application decides:
- how users interact with the application
- which Main LLM is used
- which external tools are available
- how web search is performed
- how Python or other code is executed
- how external APIs are called
- how final results are displayed

LangFORM exposes structured inputs and outputs so the application can decide how to use them.

## Tool Boundary

File-reading and information-extraction capabilities are part of LangFORM's context-processing responsibilities.

The required parser libraries may be installed and managed as dependencies rather than implemented directly inside LangFORM.

General agent tools such as web search, Python execution, shell execution, email, browser actions, and external APIs belong to the surrounding platform or agent runtime.

LangFORM may receive the results of those actions and prepare them as context for further model reasoning.

## Memory

LangFORM manages conversation and contextual memory that may be useful in future model interactions.

The framework should avoid blindly resending complete conversation history when a smaller relevant memory representation is sufficient.

## Initial Scope

Version v0.0.1 focuses on:
- terminology
- system instructions for the local SLM
- Asset registration concepts
- metadata concepts
- Context Frames
- retrieval
- conversation context
- model-to-model context orchestration
- a stable interface between LangFORM and the surrounding application

## Core Principle

LangFORM does not try to give a model more context.

LangFORM tries to give the model the right context.
