import yingAvatar from '@/assets/ying/avatar.png'
import projectorCatAvatar from '@/assets/packs/projector-cat/avatar.png'
import chibiterasuAvatar from '@/assets/packs/builtin-chibiterasu/avatar.png'
import nailongAvatar from '@/assets/packs/builtin-nailong/avatar.png'
import kurisuAvatar from '@/assets/packs/builtin-kurisu/avatar.png'
import z256KurisuAvatar from '@/assets/packs/builtin-kurisu-z256/avatar.png'

/** UI 小头像由 Vite 内联；复用原图，不依赖浏览器另取静态资源。 */
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
