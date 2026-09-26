import request from './request'

// Key 走请求头而不是查询串 —— 查询串会进服务端访问日志。
export function testTmdb({ apiKey, language }) {
  return request.get('/tmdb/test', {
    headers: {
      'X-Tmdb-Key': apiKey || '',
      'X-Tmdb-Language': language || '',
    },
  })
}

export function searchTmdb({ q, year, apiKey, language }) {
  return request.get('/tmdb/search', {
    params: { q, year },
    headers: {
      'X-Tmdb-Key': apiKey || '',
      'X-Tmdb-Language': language || '',
    },
  })
}
