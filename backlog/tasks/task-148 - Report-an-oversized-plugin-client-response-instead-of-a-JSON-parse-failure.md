---
id: TASK-148
title: Report an oversized plugin client response instead of a JSON parse failure
status: To Do
assignee: []
created_date: '2026-10-29 13:37'
labels:
  - python
  - http
milestone: m-7
dependencies: []
priority: low
type: bug
ordinal: 148000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
PluginClient._json reads at most 1 MiB of the body (response.read(1024 * 1024)) and then parses it. A well-formed 200 response larger than 1 MiB - a describe() on a large plugin, or a call() returning a big result - is silently cut mid-token and surfaces as "Unterminated string starting at: line 1 column 11", which points at the JSON text rather than at the size limit. A probe against a stub server returning 2 MiB reproduces it.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 A response that exceeds the client's read bound raises PluginClientError saying the response was too large, with the bound in the message; a test attaches a stub server with an oversized body to PluginClient.call.
- [ ] #2 A response exactly at the bound still parses, and the bound is a single named constant shared by the JSON and stream paths.
- [ ] #3 Non-goals: do not add a paging or streaming download API, and do not change the server's 1 MiB response expectations.
<!-- AC:END -->
