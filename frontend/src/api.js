export class ApiError extends Error {
  constructor(message, status) {
    super(message);
    this.status = status;
  }
}
export async function api(path, options = {}) {
  let response;
  try {
    response = await fetch(`/api${path}`, options);
  } catch (error) {
    if (error.name === "AbortError") throw error;
    throw new ApiError("无法连接本地服务，请确认后端已启动。", 0);
  }
  let data;
  try {
    data = await response.json();
  } catch {
    throw new ApiError("服务返回了无法读取的结果，请重试。", response.status);
  }
  if (!response.ok) {
    const fallback = {
      400: "文件无法处理，请检查 ZIP 内容。",
      404: "记录不存在，可能来自已清理的扫描。",
      409: "当前模式或结果格式不支持此操作。",
      413: "文件超出上传限制，请压缩项目后重试。",
      422: "筛选或上传参数不正确，请检查后重试。",
    };
    throw new ApiError(
      fallback[response.status] || "服务暂时无法完成请求，请重试。",
      response.status,
    );
  }
  return data;
}
export function uploadScan(
  file,
  onProgress,
  onAnalyzing,
  scene = "release_precheck",
  profile,
) {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open("POST", "/api/scans");
    xhr.timeout = 600000;
    xhr.upload.onprogress = (e) => {
      if (e.lengthComputable)
        onProgress(Math.round((e.loaded / e.total) * 100));
    };
    xhr.upload.onload = () => onAnalyzing();
    xhr.onerror = () => reject(new ApiError("连接中断，请检查服务后重试。", 0));
    xhr.ontimeout = () =>
      reject(
        new ApiError("等待时间较长，请先检查扫描历史，确认任务是否已完成。", 0),
      );
    xhr.onload = () => {
      let data;
      try {
        data = JSON.parse(xhr.responseText);
      } catch {
        reject(new ApiError("扫描返回异常，请检查服务状态。", xhr.status));
        return;
      }
      if (xhr.status === 201) resolve(data);
      else
        reject(
          new ApiError(
            {
              400: "ZIP 无法安全导入，请检查文件内容和大小限制。",
              413: "ZIP 超过服务上传限制。",
              422: "没有收到有效文件。",
            }[xhr.status] || "扫描未能完成，请检查服务后重试。",
            xhr.status,
          ),
        );
    };
    const form = new FormData();
    form.append("file", file);
    form.append("scene", scene);
    if (profile) form.append("profile", profile);
    xhr.send(form);
  });
}
export const encode = encodeURIComponent;
