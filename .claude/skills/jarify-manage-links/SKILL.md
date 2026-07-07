---
name: jarify-manage-links
description: Update traceability links between Jarify specifications and source code. Use this skill to inject Start/End comment tags into code and update the corresponding index.json files.
---

# Jarify: Manage Traceability Links

This skill provides the strict formatting rules for linking source code to Jarify requirements. When implementing a requirement, you MUST map it to the code using BOTH inline comments AND the `index.json` file.

## 1. Code Comments (The Anchor)

To link a block of code to a specific requirement, you MUST wrap the implementation block in exact tracking comments.

**Format:**
```typescript
// #EXT-XXX-REQ-XX Start
function myImplementation() {
    // ... code ...
}
// #EXT-XXX-REQ-XX End
```

**Crucial Formatting Restrictions:**
- The comment MUST start with `// ` (or `# ` for Python/Bash, etc. depending on the language's native line comment syntax).
- It MUST contain the exact string `#EXT-XXX-REQ-XX` where `EXT-XXX` is the Specification ID and `REQ-XX` is the Requirement ID.
- It MUST end with exactly ` Start` or ` End`. Note the space before the word.
- Do NOT use hyphens between the ID and the word (e.g., `REQ-1-Start` is INVALID).

## 2. Updating `index.json` (The Map)

After inserting or modifying the `Start`/`End` comments in the source code, you MUST update the `index.json` file located in the specification's folder (e.g., `.jarify/EXT-001/index.json`).

This file is what the Jarify VS Code extension reads to power the UI and Hover tooltips.

**Format:**
```json
{
  "REQ-1": [
    {
      "file": "src/feature.ts",
      "startLine": 45,
      "endLine": 82
    }
  ],
  "REQ-2": [
    {
      "file": "src/feature.ts",
      "startLine": 100,
      "endLine": 115
    },
    {
      "file": "src/utils.ts",
      "startLine": 10,
      "endLine": 25
    }
  ]
}
```

**Crucial Formatting Restrictions:**
- The root keys MUST be exactly the Requirement ID string (e.g., `"REQ-1"`). Do NOT include the Spec ID in the key here.
- The value MUST be an Array of objects.
- `file`: The path to the source file, strictly relative to the workspace root, using forward slashes `/`.
- `startLine`: The 1-indexed line number containing the `Start` comment.
- `endLine`: The 1-indexed line number containing the `End` comment.

## Workflow for Linking Code

Whenever you write new code or modify existing code to fulfill a requirement:
1. Identify the target Spec ID (e.g., `EXT-002`) and Requirement ID (e.g., `REQ-5`).
2. Wrap the affected code block with the exact `Start` and `End` comments.
3. Determine the final 1-indexed line numbers of those comments.
4. Add or update the corresponding entry in `.jarify/EXT-002/index.json`.
5. Double-check that the `startLine` and `endLine` in the JSON perfectly match the physical lines of the comments in the source file.
