import { describe, expect, it } from 'vitest'

import { normalizeFiniteNumber } from '../../../../plugins.v2/subscribeassistantenhanced/src/config/values'

describe('normalizeFiniteNumber', () => {
  it('将整数字符串转换为 number', () => {
    expect(normalizeFiniteNumber(10, '45')).toBe(45)
  })

  it('将小数字符串转换为 number', () => {
    expect(normalizeFiniteNumber(10, '3.75')).toBe(3.75)
  })

  it('保留已有数值输入的 number 类型和值', () => {
    const result = normalizeFiniteNumber(10, 2.5)

    expect(result).toBe(2.5)
    expect(typeof result).toBe('number')
  })

  it.each([null, undefined, '', '   ', Number.NaN, Number.POSITIVE_INFINITY, Number.NEGATIVE_INFINITY])(
    '非法输入 %s 保留最近一次有效值',
    incoming => {
      expect(normalizeFiniteNumber(10, incoming)).toBe(10)
    },
  )
})
