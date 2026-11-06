// SSE 帧解析。**零 import** —— node 可以直接加载它跑断言
// （scripts/check-rename-batch.mjs），与 renamePayload.js / renameRunner.js 同规格。
//
// 为什么不能 `text.split('\n\n')` 一次性切完: 网络分片会把一帧切成两半, 甚至切在
// 一个 UTF-8 多字节字符中间。多字节由调用方的 TextDecoder({ stream: true }) 兜住;
// 本模块只负责「字符串流 → 完整帧」这一段状态机。
//
// 只认 `data:` 行: 服务端把事件类型放在 JSON 的 `type` 里, 不额外发 `event:` 行。
// 解析端若也去认 `event:`, 就会出现「后端改了字段、前端还在按事件名分派」的分叉。

export function createSseParser() {
  let buffer = ''

  function parseBlock(block) {
    const dataLines = []
    for (const line of block.split(/\r?\n/)) {
      // 空行与 `:` 开头的注释（心跳）不承载数据
      if (!line || line.startsWith(':')) continue
      if (!line.startsWith('data:')) continue
      // 规范允许 `data:value` 与 `data: value` 两种写法, 前导**一个**空格属于
      // 分隔符而不是数据 —— 多剥会把以空格开头的 JSON 弄坏（这里不会发生, 但
      // 规则仍按规范写, 免得将来有人用多行 data 时踩到）。
      dataLines.push(line.slice(5).replace(/^ /, ''))
    }
    if (!dataLines.length) return null

    const raw = dataLines.join('\n')
    try {
      return JSON.parse(raw)
    } catch (error) {
      // **不静默丢帧**: 丢掉一帧进度只会让进度条卡住, 丢掉 result 帧会让整批
      // 结果显示成「没有结果」—— 那比报错难查得多。
      throw new Error(`SSE 数据不是合法 JSON: ${raw.slice(0, 200)}`)
    }
  }

  return {
    /** 喂一段文本，返回本次凑齐的完整帧（可能 0 到多帧）。 */
    feed(text) {
      buffer += text
      const messages = []
      for (;;) {
        const match = /\r?\n\r?\n/.exec(buffer)
        if (!match) break
        const block = buffer.slice(0, match.index)
        buffer = buffer.slice(match.index + match[0].length)
        const message = parseBlock(block)
        if (message !== null) messages.push(message)
      }
      return messages
    },
    /**
     * 流结束时把残留的一帧解析出来。
     *
     * 正常服务端每帧都以空行收尾, 所以这里通常是空的; 但「最后一帧没有结尾空行」
     * 是 SSE 里常见的手写实现, 静默丢掉它就等于丢掉 result 帧。
     */
    flush() {
      const rest = buffer
      buffer = ''
      if (!rest.trim()) return []
      const message = parseBlock(rest)
      return message === null ? [] : [message]
    },
  }
}
