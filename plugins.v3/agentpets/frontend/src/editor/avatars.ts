import yingAvatar from '@/assets/ying/avatar.png'
import projectorCatAvatar from '@/assets/packs/projector-cat/avatar.png'

/** UI 小头像由 Vite 内联；复用原图，不依赖浏览器另取静态资源。 */
const AVATARS: Readonly<Record<string, string>> = {
  ying: yingAvatar,
  'projector-cat': projectorCatAvatar,
}

export function builtinAvatar(key: string): string {
  return AVATARS[key] ?? ''
}
