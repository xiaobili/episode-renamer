import request from './request'
import { createSseParser } from './sse'

export function previewRename(data) {
  return request.post('/rename/preview', data)
}

export function executeRename(data) {
  return request.post('/rename/execute', data)
}

// 整批一次执行（OpenList 源）。**不是 axios**: 响应是 `text/event-stream`,
// axios 会把整个流缓冲到最后才交付 —— 那样进度条只会在结束时跳满一次, 等于没有。
//
// 并发数、请求间隔、批次内重名降级、执行 → NFO 收尾 → 目录改名的顺序全部在后端
// （见 backend/app/core/openlist_batch.py）。这里只做两件事: 发一次请求, 把帧转成
// 进度回调与最终结果。
//
// 返回的 result 与 `BatchRenameResult` **同形**, 结果对话框无需为它改判据。
export async function executeRenameBatch(data, { onProgress } = {}) {
  const response = await fetch('/api/rename/batch-execute', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', Accept: 'text/event-stream' },
    body: JSON.stringify(data),
  })

  if (!response.ok) {
    // 后端的配置类错误在 detail 里（401「请先连接 OpenList」/ 400「仅支持 ...」）。
    // 它是用户唯一能看出「该做什么」的地方, 不能降级成一句 HTTP 状态码。
    let detail = `批量执行失败（HTTP ${response.status}）`
    try {
      const body = await response.json()
      if (body?.detail) detail = body.detail
    } catch { /* 非 JSON 错误体: 保留上面那句带状态码的文案 */ }
    throw new Error(detail)
  }
  if (!response.body) throw new Error('浏览器不支持流式响应，无法显示执行进度')

  const reader = response.body.getReader()
  const decoder = new TextDecoder()
  const parser = createSseParser()
  let result = null
  let failure = null

  const consume = (messages) => {
    for (const message of messages) {
      if (message.type === 'start') {
        // done 归零由调用方负责（它与「遮罩打开」同一拍）; 这里只同步总数,
        // 免得首帧之前进度条按上一次的 total 显示。
        onProgress?.({ done: 0, total: message.total, current: '' })
      } else if (message.type === 'progress') {
        onProgress?.({
          done: message.done, total: message.total, current: message.current || '',
        })
      } else if (message.type === 'result') {
        result = message.result
      } else if (message.type === 'error') {
        // 批次级硬失败。单个文件的失败在 result.results 里, 不走这一支。
        failure = new Error(message.detail || '批量执行失败')
      }
    }
  }

  for (;;) {
    const { done, value } = await reader.read()
    if (done) break
    consume(parser.feed(decoder.decode(value, { stream: true })))
  }
  consume(parser.feed(decoder.decode()))
  consume(parser.flush())

  if (failure) throw failure
  if (!result) throw new Error('批量执行没有返回结果')
  return result
}

export function dryRunRename(data) {
  return request.post('/rename/dry-run', data)
}

export function finalizeRename(data) {
  return request.post('/rename/finalize', data)
}

// 剧集文件夹改名（批次级）。**必须在 finalize 之后**调用 —— 先改目录会让 NFO
// 的写盘在旧名下把目录重建出来。详见后端 core/show_folder.py 的模块注释。
export function renameShowFolders(data) {
  return request.post('/rename/folders', data)
}
