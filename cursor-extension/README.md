# Dispatch Cursor Extension (Scaffold)

This extension collects local editor context and sends it to the Dispatch Companion localhost bridge.

## Current scaffold behavior

- Registers command: `Dispatch: Send Context To Companion`
- Reads active editor file path + selected text
- Sends payload to companion localhost endpoint:
  - `POST http://127.0.0.1:43111/context`

## Expected companion local bridge endpoint

`POST /context`

```json
{
  "projectId": "uuid",
  "filePath": "/abs/path/file.ts",
  "selection": "selected code",
  "diagnostics": "lint or language-server diagnostics text"
}
```

