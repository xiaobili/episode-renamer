import request from './request'

export function getPresets() {
  return request.get('/presets')
}

export function validateTemplate(template) {
  return request.post('/validate', { template })
}
