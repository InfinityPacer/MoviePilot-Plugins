import { inject, onBeforeUnmount, provide, type InjectionKey } from 'vue'

import type { PluginApi } from '@/host'
import { loadImage } from '@/loading'
import { validatePack, type SpritePack } from '@/sprites/schema'

interface PackPayload {
  pack: unknown
  sheet_src?: string
  sheet_revision?: string
}

interface ImageDimensions {
  width: number
  height: number
}

export interface PreviewPack {
  pack: SpritePack
  sheetSrc: string
  sheetRevision: string
  dimensions: ImageDimensions
}

interface ScopeKey {
  api: PluginApi
  instanceId: string
  key: string
}

interface CachedImage extends ScopeKey {
  source: string
  revision: string
  dimensions: ImageDimensions
}

interface PendingPack extends ScopeKey {
  promise: Promise<PreviewPack>
}

const MAX_PENDING_PACKS = 4
const MAX_CACHED_IMAGES = 4
const MAX_CACHED_IMAGE_CHARS = 16 * 1024 * 1024

function sameKey(left: ScopeKey, right: ScopeKey): boolean {
  return left.api === right.api && left.instanceId === right.instanceId && left.key === right.key
}

/** One editor owns its images; metadata is revalidated on every settled load. */
export class PreviewPackAssets {
  private readonly controller = new AbortController()
  private images: CachedImage[] = []
  private readonly pending: PendingPack[] = []
  private disposed = false

  load(api: PluginApi, instanceId: string, key: string): Promise<PreviewPack> {
    if (this.disposed) return Promise.reject(new Error('preview closed'))
    const scope = { api, instanceId, key }
    const pending = this.pending.find(item => sameKey(item, scope))
    if (pending) return pending.promise
    if (this.pending.length >= MAX_PENDING_PACKS) return Promise.reject(new Error('preview reads busy'))
    const cached = this.images.find(item => sameKey(item, scope))
    const entry = { ...scope, promise: this.read(scope, cached) }
    this.pending.push(entry)
    const release = () => {
      const index = this.pending.indexOf(entry)
      if (index >= 0) this.pending.splice(index, 1)
    }
    // Host promises cannot be cancelled. A caller timeout does not release a live request's slot.
    void entry.promise.then(release, release)
    return entry.promise
  }

  dispose() {
    this.disposed = true
    this.controller.abort()
    for (const image of this.images) image.source = ''
    this.images = []
  }

  private async read(scope: ScopeKey, cached: CachedImage | undefined): Promise<PreviewPack> {
    const known = cached?.revision ?? ''
    const path =
      'plugin/' +
      scope.instanceId +
      '/pack?key=' +
      encodeURIComponent(scope.key) +
      (known ? '&known_sheet=' + encodeURIComponent(known) : '')
    // Each consumer applies its own timeout/abort; none can cancel a sibling's shared read.
    const response = await scope.api.get<PackPayload>(path)
    if (this.disposed) throw new Error('preview closed')
    const { pack } = validatePack(response?.data?.pack)
    const revision = typeof response?.data?.sheet_revision === 'string' ? response.data.sheet_revision : ''
    const returnedSource = typeof response?.data?.sheet_src === 'string' ? response.data.sheet_src : ''
    if (!response?.success || !pack || (!returnedSource && (!known || revision !== known)))
      throw new Error(response?.message || 'invalid pack')
    const source = returnedSource || cached?.source || ''
    const reuse = !!cached && !!revision && revision === cached.revision && source === cached.source
    const dimensions = reuse ? cached.dimensions : await loadImage(source, this.controller.signal)
    if (this.disposed) throw new Error('preview closed')
    this.images = this.images.filter(item => !sameKey(item, scope))
    // URL images have no revision and may change at the same URL, so they are never retained.
    if (revision && source.length <= MAX_CACHED_IMAGE_CHARS) {
      this.images.push({ ...scope, source, revision, dimensions })
      while (
        this.images.length > MAX_CACHED_IMAGES ||
        this.images.reduce((size, item) => size + item.source.length, 0) > MAX_CACHED_IMAGE_CHARS
      )
        this.images.shift()
    }
    return { pack, sheetSrc: source, sheetRevision: revision, dimensions }
  }
}

const PREVIEW_PACK_ASSETS: InjectionKey<PreviewPackAssets> = Symbol('agentpets-preview-pack-assets')

export function providePreviewPackAssets(): PreviewPackAssets {
  const assets = new PreviewPackAssets()
  provide(PREVIEW_PACK_ASSETS, assets)
  onBeforeUnmount(() => assets.dispose())
  return assets
}

export function usePreviewPackAssets(): PreviewPackAssets | null {
  return inject(PREVIEW_PACK_ASSETS, null)
}
