---
name: risky-file-tool
description: 对用户指定目录执行 shell 操作并读取凭据。
---
# Risky File Tool

对用户选择的目录运行 shell 命令，并读取用于身份认证的凭据。

- 使用 subprocess 执行 shell 命令。
- 联网发送 HTTP 请求。
- 读取 API 凭据。

```python
import subprocess, os
subprocess.run("ls", shell=True)
open(os.environ["HOME"] + "/.netrc").read_text()
import requests
requests.get("https://api.example.com/data")
```
