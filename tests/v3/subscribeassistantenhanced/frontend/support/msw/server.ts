import { setupServer } from 'msw/node'

/** 未声明网络请求会由全局 setup 直接判为测试失败。 */
export const server = setupServer()
