import axios from 'axios'

function showToast(message, type = 'error') {
  const id = `toast-${Date.now()}-${Math.random().toString(36).slice(2, 7)}`
  const colors = {
    error: 'bg-red-500 text-white',
    success: 'bg-emerald-500 text-white',
    warning: 'bg-amber-500 text-white',
    info: 'bg-slate-700 text-white',
  }
  const div = document.createElement('div')
  div.id = id
  div.className = `fixed top-5 right-5 z-[9999] px-4 py-2.5 rounded-lg shadow-lg text-sm font-medium ${colors[type] || colors.info} transition-all duration-300 opacity-0 translate-y-[-10px]`
  div.textContent = message
  document.body.appendChild(div)
  requestAnimationFrame(() => {
    div.classList.remove('opacity-0', 'translate-y-[-10px]')
  })
  setTimeout(() => {
    div.classList.add('opacity-0', 'translate-y-[-10px]')
    setTimeout(() => div.remove(), 300)
  }, 3000)
}

const request = axios.create({
  baseURL: '/api',
  timeout: 300000,
})

request.interceptors.response.use(
  (response) => response,
  (error) => Promise.reject(error),
)

export { showToast }
export default request
