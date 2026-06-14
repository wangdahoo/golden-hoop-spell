# Context Snapshot Guide

This guide defines the format and extraction process for the project context snapshot used by ghs-plan subagents. The snapshot is a condensed summary of the project's architecture that subagents read instead of independently scanning the codebase.

## Purpose

The snapshot serves as a **shared knowledge base** between the plan designer and plan reviewer. It is created once before any subagent work and read by all subagents across all rounds. This eliminates redundant codebase exploration and saves significant token overhead.

## Snapshot Format

```markdown
# Project Context Snapshot

## 1. Technology Stack
- **Language**: <language and version>
- **Runtime/Framework**: <runtime/framework and version>
- **Key dependencies**: <list notable libraries with versions>
- **Build system**: <build tool and config>
- **Test framework**: <testing tool>

## 2. Directory Structure

<annotated file tree with one-line descriptions for key files>

## 3. Architecture Summary

### Entry Point
<how the app starts, initialization flow>

### Module Responsibilities
<one paragraph per major module describing what it does>

### Data Model
<tables/schemas/types with field lists>

### Key Patterns
<middleware chains, auth flow, error handling conventions, etc.>

## 4. Relevant Code Excerpts

<function signatures, database schemas, routing setup, config sections
that are directly relevant to the requirement being planned>
```

## Extraction Guidelines

### Conciseness Target

Aim for **50-70% compression** compared to reading raw source files. The snapshot should capture understanding, not reproduce code verbatim.

**Good** (summarized):
```
### Module Responsibilities
`src/routes/users.ts` — Express router with CRUD endpoints for users. Uses middleware
chain: auth -> validate -> handler. All handlers follow the pattern: extract params,
call service, return {data} or {error}.
```

**Bad** (verbatim):
```
### Module Responsibilities
```typescript
// full 80-line file contents pasted here
```
```

### Relevance Filter

Only include code excerpts that could **possibly relate to the requirement**. For a requirement about "adding tags to posts":
- Include: post model definition, post routes, tag-related types
- Exclude: auth module, payment processing, email service

### What to Include

1. **Function signatures** of public APIs (not internal implementations)
2. **Database schemas** (field names and types, not migration boilerplate)
3. **Configuration** (environment variables, config file structure)
4. **Routing setup** (endpoint paths and their handlers)
5. **Type/interface definitions** relevant to the requirement

### What NOT to Include

1. Full file contents (use summaries instead)
2. Import statements
3. Boilerplate code
4. Test files (mention their existence and framework only)
5. Generated files (build output, lock files)

## Extraction Process

When creating the snapshot, follow this order:

1. **Read dependency manifest**: `package.json`, `requirements.txt`, `Cargo.toml`, etc.
2. **Get directory structure**: `find . -type f` (exclude node_modules, .git, build dirs)
3. **Read entry point**: `src/index.ts`, `main.py`, `src/lib.rs`, etc.
4. **Read config files**: `.env.example`, config modules, database setup
5. **Read requirement-relevant files**: files in directories that relate to the requirement topic
6. **Summarize and write**: Condense findings into the snapshot format
