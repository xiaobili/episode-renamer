import request from './request'

export function openlistLogin(data) {
  return request.post('/openlist/login', data)
}

export function openlistTest(data) {
  return request.post('/openlist/test', data)
}

export function openlistStatus() {
  return request.get('/openlist/status')
}

export function openlistMounts() {
  return request.get('/openlist/mounts')
}

export function openlistLogout() {
  return request.post('/openlist/logout')
}

export function openlistBrowse(path) {
  return request.post('/openlist/browse', { path })
}
