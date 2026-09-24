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
