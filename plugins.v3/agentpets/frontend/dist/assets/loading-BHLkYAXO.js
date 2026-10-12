function withLoadTimeout(operation, signal, timeout = 5e3) {
  return new Promise((resolve, reject) => {
    const cleanup = () => {
      window.clearTimeout(timer);
      signal.removeEventListener("abort", abort);
    };
    const abort = () => {
      cleanup();
      reject(new Error("loading cancelled"));
    };
    const timer = window.setTimeout(() => {
      cleanup();
      reject(new Error("loading timed out"));
    }, timeout);
    signal.addEventListener("abort", abort, { once: true });
    operation.then(
      (value) => {
        cleanup();
        resolve(value);
      },
      (error) => {
        cleanup();
        reject(error);
      }
    );
    if (signal.aborted) abort();
  });
}
async function loadImage(src, signal) {
  const image = new Image();
  try {
    return await withLoadTimeout(
      new Promise((resolve, reject) => {
        image.onload = () => {
          const width = image.naturalWidth;
          const height = image.naturalHeight;
          if (!Number.isFinite(width) || !Number.isFinite(height) || width <= 0 || height <= 0)
            reject(new Error("invalid image dimensions"));
          else resolve({ width, height });
        };
        image.onerror = () => reject(new Error("image unavailable"));
        image.src = src;
      }),
      signal
    );
  } finally {
    image.onload = null;
    image.onerror = null;
  }
}

export { loadImage as l, withLoadTimeout as w };
