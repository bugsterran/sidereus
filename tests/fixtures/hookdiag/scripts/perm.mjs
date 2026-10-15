const out = { hookSpecificOutput: { hookEventName: "PermissionRequest", decision: { behavior: "deny", message: "no" } } };
process.stdout.write(JSON.stringify(out));
