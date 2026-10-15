---
name: never-execute
description: A skill whose inline script must never be executed by the scanner.
---
# Never Execute

This fixture contains code that raises if executed. The static parser must only
use AST and never run it.

```python
raise RuntimeError("THIS FILE MUST NEVER EXECUTE")
import os
os.system("echo pwned")
```
