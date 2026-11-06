// SSE 解析与批量载荷的判据。
//
// 为什么单独一个脚本: 这两块都是**纯函数**, 但它们的错误方式都是「静默」的 ——
// 少解析一帧只让进度条卡住, 丢掉 result 帧会让整批结果显示成「没有结果」,
// 而载荷少一个字段会让「勾了没生效」。运行期判据（check-execute-behaviour.mjs）
// 用的是整块响应一次到达, 覆盖不到「分片切在半帧中间」这条真实网络的常态。
//
// 零依赖: 只 import src 下的零 import 模块（node 可直接加载）。

import { createSseParser } from '../src/api/sse.js'
import { buildRenamePayload } from '../src/stores/renamePayload.js'

const results = []
function check(name, cond, extra = '') {
  results.push(`${cond ? 'PASS' : 'FAIL'} ${name}${cond ? '' : '  <<< ' + extra}`)
}

const frame = obj => `data: ${JSON.stringify(obj)}\n\n`

// ---------------------------------------------------------------------------
// 1. 一帧、多帧、切在半帧中间
// ---------------------------------------------------------------------------
{
  const parser = createSseParser()
  const messages = parser.feed(frame({ type: 'progress', done: 1, total: 3 }))
  check('单帧单块', messages.length === 1 && messages[0].done === 1,
    JSON.stringify(messages))
}

{
  const parser = createSseParser()
  const text = frame({ type: 'progress', done: 1, total: 2 }) +
    frame({ type: 'result', result: { executed: 2 } })
  const messages = parser.feed(text)
  check('一个块里的两帧都被解析', messages.length === 2 &&
    messages[1].type === 'result', JSON.stringify(messages))
}

{
  // 真实网络的分片不会照顾帧边界 —— 这里把一帧切成三段, 其中一段切在 JSON 里。
  const whole = frame({ type: 'progress', done: 2, total: 5, current: 'Show.S01E02.mkv' })
  const parser = createSseParser()
  const parts = [whole.slice(0, 7), whole.slice(7, 33), whole.slice(33)]
  const collected = parts.flatMap(part => parser.feed(part))
  check('跨块的一帧只在凑齐后交付一次', collected.length === 1 &&
    collected[0].current === 'Show.S01E02.mkv', JSON.stringify(collected))
  check('跨块解析后缓冲区已清空', parser.flush().length === 0)
}

{
  const parser = createSseParser()
  const collected = parser.feed(
    'data: {"type":"progress","done":1}\r\n\r\n' +
    'data: {"type":"progress","done":2}\r\n\r\n',
  )
  check('CRLF 分帧同样有效', collected.length === 2 && collected[1].done === 2,
    JSON.stringify(collected))
}

// ---------------------------------------------------------------------------
// 2. 注释 / 心跳 / 无空格写法 / 多行 data
// ---------------------------------------------------------------------------
{
  const parser = createSseParser()
  const collected = parser.feed(': keep-alive\n\ndata:{"type":"start","total":1}\n\n')
  check('注释（心跳）被忽略，无空格 data 仍解析',
    collected.length === 1 && collected[0].total === 1, JSON.stringify(collected))
}

{
  const parser = createSseParser()
  const collected = parser.feed('data: {"type":"result",\ndata: "result":{"a":1}}\n\n')
  check('多行 data 按规范用换行拼接',
    collected.length === 1 && collected[0].result.a === 1, JSON.stringify(collected))
}

{
  const parser = createSseParser()
  const collected = parser.feed('event: progress\ndata: {"type":"progress","done":1}\n\n')
  check('event: 行不参与分派（类型在 JSON 的 type 里）',
    collected.length === 1 && collected[0].type === 'progress', JSON.stringify(collected))
}

// ---------------------------------------------------------------------------
// 3. 收尾与坏数据
// ---------------------------------------------------------------------------
{
  // 手写实现常常最后一帧没有结尾空行 —— 静默丢掉它就等于丢掉 result 帧。
  const parser = createSseParser()
  const early = parser.feed('data: {"type":"result","result":{"executed":3}}')
  check('没有结尾空行时 feed 不交付', early.length === 0)
  const flushed = parser.flush()
  check('flush 交出残留的一帧', flushed.length === 1 &&
    flushed[0].result.executed === 3, JSON.stringify(flushed))
}

{
  const parser = createSseParser()
  let threw = null
  try {
    parser.feed('data: {not json}\n\n')
  } catch (error) {
    threw = error
  }
  check('坏 JSON 抛错（不静默丢帧）', threw instanceof Error,
    threw ? threw.message : '没有抛错')
}

// ---------------------------------------------------------------------------
// 4. 批量载荷（mode: 'batch'）
// ---------------------------------------------------------------------------
const base = {
  source: 'openlist',
  path: '/m/S',
  template: '{show} - S{season_padded}E{episode_padded}{extension}',
  folderTemplate: 'Season {season_padded}',
  createSeasonFolder: false,
  conflictStrategy: 'skip',
  episodePadDigits: 2,
  seasonPadDigits: 2,
  tmdb: { apiKey: 'k', language: 'zh-CN', enabled: true },
  tmdbOverrides: {},
  scraped: true,
  generateNfo: true,
  nfoOverwrite: false,
  generateStrm: true,
  strm: { mode: 'local', baseUrl: 'http://ol', localRoot: '/m/strm', remoteRoot: '' },
  strmScanRoot: '/m/S',
  openlistMaxConcurrent: 3,
  openlistRequestInterval: 0.5,
  renameFolders: true,
}

{
  const payload = buildRenamePayload({
    ...base, mode: 'batch', fileIds: ['f1', 'f2'], overrides: { f1: { episode: 3 } },
  })
  check('batch 载荷用 file_ids（不是单数 file_id）',
    Array.isArray(payload.file_ids) && payload.file_ids.length === 2 &&
      !('file_id' in payload), JSON.stringify(Object.keys(payload)))
  check('batch 载荷带冲突策略', payload.conflict_strategy === 'skip')
  check('batch 载荷带限流设置',
    payload.openlist_max_concurrent === 3 && payload.openlist_request_interval === 0.5)
  check('batch 载荷带 STRM 五项',
    payload.generate_strm === true && payload.strm_mode === 'local' &&
      payload.strm_local_root === '/m/strm' && payload.strm_scan_root === '/m/S')
  check('batch 载荷带 rename_folders', payload.rename_folders === true)
  check('batch 载荷带预览同源的模板字段',
    payload.folder_template === 'Season {season_padded}' &&
      payload.episode_pad_digits === 2)
}

{
  let threw = null
  try {
    buildRenamePayload({ ...base, mode: 'batch', overrides: {} })
  } catch (error) {
    threw = error
  }
  check('batch 缺 fileIds 时抛错（不静默发一份空批次）', threw instanceof Error,
    threw ? threw.message : '没有抛错')
}

console.log(results.join('\n'))
const failed = results.filter(r => r.startsWith('FAIL')).length
console.log(failed ? `\n${failed} 项失败 / 共 ${results.length} 项` : `\n全部通过（${results.length} 项）`)
process.exit(failed ? 1 : 0)
