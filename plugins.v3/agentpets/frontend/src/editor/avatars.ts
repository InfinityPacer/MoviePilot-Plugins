import yingAvatar from '@/assets/ying/avatar.ui.webp'
import projectorCatAvatar from '@/assets/packs/projector-cat/avatar.ui.webp'
import chibiterasuAvatar from '@/assets/packs/builtin-chibiterasu/avatar.ui.webp'
import nailongAvatar from '@/assets/packs/builtin-nailong/avatar.ui.webp'
import kurisuAvatar from '@/assets/packs/builtin-kurisu/avatar.ui.webp'
import z256KurisuAvatar from '@/assets/packs/builtin-kurisu-z256/avatar.ui.webp'

/** UI 小头像由 Vite 内联；使用保留原像素的无损 WebP，不依赖浏览器另取静态资源。 */
const AVATARS: Readonly<Record<string, string>> = {
  ying: yingAvatar,
  'projector-cat': projectorCatAvatar,
  'builtin-chibiterasu': chibiterasuAvatar,
  'builtin-nailong': nailongAvatar,
  'builtin-kurisu': kurisuAvatar,
  'builtin-kurisu-z256': z256KurisuAvatar,
}

export function builtinAvatar(key: string): string {
  return AVATARS[key] ?? ''
}
