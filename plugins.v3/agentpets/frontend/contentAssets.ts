import { createHash } from 'node:crypto'
import { Buffer } from 'node:buffer'
import type { Plugin } from 'vite'

export interface ContentFile {
  path: string
  content: Uint8Array
}

/** Hash final filenames and bytes, independently of build time and absolute workspace paths. */
export function contentIdentity(files: readonly ContentFile[]): string {
  const hash = createHash('sha256')
  for (const file of [...files].sort((a, b) => (a.path < b.path ? -1 : a.path > b.path ? 1 : 0))) {
    hash.update(file.path).update('\0').update(String(file.content.byteLength)).update('\0').update(file.content)
  }
  return hash.digest('hex')
}

/** Publish the entire relative resource graph under one content identity. */
export function contentAssets(): Plugin {
  return {
    name: 'agentpets-content-assets',
    enforce: 'post',
    generateBundle: {
      order: 'post',
      handler(_options, bundle) {
        const entries = Object.entries(bundle).filter(([name]) => name.startsWith('assets/'))
        if (!entries.some(([name]) => name === 'assets/remoteEntry.js')) throw new Error('Missing federation entry')
        const files = entries.map(([name, entry]) => ({
          path: name.slice('assets/'.length),
          content: Buffer.from(entry.type === 'chunk' ? entry.code : entry.source),
        }))
        const buildId = contentIdentity(files)
        const directory = 'assets/build-' + buildId
        for (const [name, entry] of entries) {
          const published = directory + '/' + name.slice('assets/'.length)
          bundle[published] = { ...entry, fileName: published }
          // Original image/pack URLs are public compatibility paths; code uses the content graph.
          if (!/\.(png|webp|json)$/.test(name)) delete bundle[name]
        }
        this.emitFile({
          type: 'asset',
          fileName: 'asset-manifest.json',
          source:
            JSON.stringify(
              {
                schema_version: 1,
                build_id: buildId,
                asset_directory: directory,
                files: files
                  .map(file => ({
                    path: file.path,
                    bytes: file.content.byteLength,
                    sha256: createHash('sha256').update(file.content).digest('hex'),
                  }))
                  .sort((a, b) => (a.path < b.path ? -1 : a.path > b.path ? 1 : 0)),
              },
              null,
              2,
            ) + '\n',
        })
        this.emitFile({
          type: 'asset',
          fileName: 'assets/remoteEntry.js',
          source:
            'export { get, init, dynamicLoadingCss } from ' +
            JSON.stringify('./build-' + buildId + '/remoteEntry.js') +
            ';\n',
        })
      },
    },
  }
}
