/** 请求超时或组件卸载后停止等待，迟到的响应不会覆盖回退状态。 */
export function withLoadTimeout<T>(operation: Promise<T>, signal: AbortSignal, timeout = 5000): Promise<T> {
  return new Promise((resolve, reject) => {
    const cleanup = () => {
      window.clearTimeout(timer)
      signal.removeEventListener('abort', abort)
    }
    const abort = () => {
      cleanup()
      reject(new Error('loading cancelled'))
    }
    const timer = window.setTimeout(() => {
      cleanup()
      reject(new Error('loading timed out'))
    }, timeout)
    signal.addEventListener('abort', abort, { once: true })
    operation.then(
      value => {
        cleanup()
        resolve(value)
      },
      error => {
        cleanup()
        reject(error)
      },
    )
    if (signal.aborted) abort()
  })
}

/** CSS 背景图也要确认图片加载结果，JSON 请求成功不等于图片可显示。 */
export async function loadImage(src: string, signal: AbortSignal): Promise<{ width: number; height: number }> {
  const image = new Image()
  try {
    return await withLoadTimeout(
      new Promise((resolve, reject) => {
        image.onload = () => {
          const width = image.naturalWidth
          const height = image.naturalHeight
          if (!Number.isFinite(width) || !Number.isFinite(height) || width <= 0 || height <= 0)
            reject(new Error('invalid image dimensions'))
          else resolve({ width, height })
        }
        image.onerror = () => reject(new Error('image unavailable'))
        image.src = src
      }),
      signal,
    )
  } finally {
    image.onload = null
    image.onerror = null
  }
}
