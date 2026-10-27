import request from './request'

export function previewRename(data) {
  return request.post('/rename/preview', data)
}

export function executeRename(data) {
  return request.post('/rename/execute', data)
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
