/** 将动态数值输入归一化为有限 number；空值或非法值保留最近一次有效值。 */
export function normalizeFiniteNumber(current: number, incoming: unknown): number {
  if (incoming === null || incoming === undefined) return current
  if (typeof incoming === 'string' && !incoming.trim()) return current
  const parsed = typeof incoming === 'number' ? incoming : Number(incoming)
  return Number.isFinite(parsed) ? parsed : current
}
