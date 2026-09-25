import request from './request'

export function scanDirectory(data) {
  return request.post('/scan', data)
}

export function browseLocalDirectory(path) {
  return request.post('/browse', { path })
}

export function getCachedFiles() {
  return request.get('/files')
}

export function clearFiles() {
  return request.delete('/files')
}
