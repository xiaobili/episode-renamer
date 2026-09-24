import request from './request'

export function parseSingle(data) {
  return request.post('/parse', data)
}

export function parseBatch(data) {
  return request.post('/parse/batch', data)
}
