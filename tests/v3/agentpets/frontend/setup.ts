import '@testing-library/jest-dom/vitest'

import { cleanup } from '@testing-library/vue'
import { afterEach, beforeEach, vi } from 'vitest'
import { executeArchiveJob, type ArchiveJob } from '@/sprites/archiveCodec'
import { GREETING_MARKER } from '@/stage/greeting'

// Vuetify 组件依赖这两个浏览器接口，jsdom 没有提供。
class ResizeObserverStub implements ResizeObserver {
  disconnect() {}
  observe() {}
  unobserve() {}
}

class IntersectionObserverStub implements IntersectionObserver {
  readonly root = null
  readonly rootMargin = '0px'
  readonly thresholds = [0]

  disconnect() {}
  observe() {}
  takeRecords(): IntersectionObserverEntry[] {
    return []
  }
  unobserve() {}
}

Object.defineProperty(globalThis, 'ResizeObserver', { configurable: true, value: ResizeObserverStub, writable: true })
Object.defineProperty(globalThis, 'IntersectionObserver', {
  configurable: true,
  value: IntersectionObserverStub,
  writable: true,
})
Object.defineProperty(window, 'matchMedia', {
  configurable: true,
  value: (query: string): MediaQueryList => ({
    addEventListener: vi.fn(),
    addListener: vi.fn(),
    dispatchEvent: vi.fn(),
    matches: false,
    media: query,
    onchange: null,
    removeEventListener: vi.fn(),
    removeListener: vi.fn(),
  }),
  writable: true,
})

afterEach(() => {
  cleanup()
  vi.useRealTimers()
  vi.restoreAllMocks()
  vi.unstubAllGlobals()
})

// jsdom 不解码图片；普通用例模拟成功加载，故障测试按需覆盖 Image。
beforeEach(() => {
  // Ordinary behavior tests start after the one-shot greeting; dedicated cases clear this marker.
  Reflect.defineProperty(document, GREETING_MARKER, { value: true, configurable: true })
  class CodecWorker {
    onmessage: ((event: { data: unknown }) => void) | null = null
    onerror = null
    onmessageerror = null
    stopped = false
    terminate() {
      this.stopped = true
    }
    postMessage(job: ArchiveJob) {
      void Promise.resolve().then(() => {
        if (this.stopped) return
        try {
          this.onmessage?.({ data: { success: true, result: executeArchiveJob(job) } })
        } catch (error) {
          this.onmessage?.({ data: { success: false, error: (error as Error).message } })
        }
      })
    }
  }
  vi.stubGlobal('Worker', CodecWorker)
  class LoadedImage {
    onload: (() => void) | null = null
    onerror: (() => void) | null = null
    naturalWidth = 1536
    naturalHeight = 2288
    set src(value: string) {
      if (value.includes('projector-cat')) {
        this.naturalWidth = 512
        this.naturalHeight = 256
      }
      void Promise.resolve().then(() => this.onload?.())
    }
  }
  vi.stubGlobal('Image', LoadedImage)
})
